"""Tests for mi6.core.crypto (RF-2.5, RF-2.6, RF-3.3, RNF-1; plan, sections 2.4 and 6.3)."""

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata

from cryptography.fernet import Fernet

from mi6.core import crypto, operations
from mi6.core.errors import AuthenticationError, CorruptDataError
from mi6.core.validation import normalize_report
from tests.test_base import FAST_ITERATIONS, MI6TestCase

PASSWORD = "clave-segura-1"
WRONG_PASSWORD = "clave-segura-2"
REPORT = "Ñandú 🦩 en Estambul"


def flip_bit(token: str, index: int) -> str:
    data = bytearray(base64.urlsafe_b64decode(token))
    data[index] ^= 0x01
    return base64.urlsafe_b64encode(bytes(data)).decode("ascii")


class CryptoTestCase(MI6TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.salt = bytes(range(16))
        self.key = crypto.derive_key(PASSWORD, self.salt, FAST_ITERATIONS)


class ConstantsTest(CryptoTestCase):
    def test_values(self) -> None:
        self.assertEqual(crypto.DEFAULT_ITERATIONS, 600_000)
        self.assertEqual(crypto.SALT_SIZE, 16)
        self.assertEqual(crypto.KEY_CHECK_PLAINTEXT, b"mi6:key-check:v1")

    def test_derive_key_defaults_to_production_iterations(self) -> None:
        self.assertEqual(crypto.derive_key.__defaults__, (600_000,))


class SaltTest(CryptoTestCase):
    def test_new_salt_has_16_random_bytes(self) -> None:
        salts = {crypto.new_salt() for _ in range(50)}
        self.assertEqual(len(salts), 50)
        for salt in salts:
            self.assertIsInstance(salt, bytes)
            self.assertEqual(len(salt), 16)

    def test_encode_decode_round_trip(self) -> None:
        text = crypto.encode_salt(self.salt)
        self.assertEqual(text, base64.b64encode(self.salt).decode("ascii"))
        self.assertEqual(len(text), 24)
        self.assertEqual(crypto.decode_salt(text), self.salt)

    def test_decode_rejects_malformed(self) -> None:
        cases = [
            "",
            "not base64!",
            base64.b64encode(bytes(15)).decode(),
            base64.b64encode(bytes(17)).decode(),
            base64.urlsafe_b64encode(b"\xfb" * 16).decode(),
            "ñ" * 24,
        ]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    crypto.decode_salt(text)

    def test_encode_rejects_wrong_size(self) -> None:
        for salt in (b"", bytes(15), bytes(17)):
            with self.subTest(size=len(salt)):
                with self.assertRaises(ValueError):
                    crypto.encode_salt(salt)


class DeriveKeyTest(CryptoTestCase):
    def test_matches_pbkdf2_reference(self) -> None:
        expected = base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac("sha256", PASSWORD.encode("utf-8"), self.salt, FAST_ITERATIONS, dklen=32)
        )
        self.assertEqual(self.key, expected)

    def test_is_a_valid_fernet_key(self) -> None:
        self.assertEqual(len(self.key), 44)
        Fernet(self.key)

    def test_is_deterministic(self) -> None:
        self.assertEqual(crypto.derive_key(PASSWORD, self.salt, FAST_ITERATIONS), self.key)

    def test_depends_on_password_salt_and_iterations(self) -> None:
        variants = [
            crypto.derive_key(WRONG_PASSWORD, self.salt, FAST_ITERATIONS),
            crypto.derive_key(PASSWORD, bytes(16), FAST_ITERATIONS),
            crypto.derive_key(PASSWORD, self.salt, FAST_ITERATIONS + 1),
        ]
        for variant in variants:
            self.assertNotEqual(variant, self.key)
        self.assertEqual(len(set(variants)), 3)

    def test_nfc_and_nfd_passwords_give_same_key(self) -> None:
        nfc = "contraseña-ñandú"
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(
            crypto.derive_key(nfc, self.salt, FAST_ITERATIONS),
            crypto.derive_key(nfd, self.salt, FAST_ITERATIONS),
        )

    def test_rejects_invalid_iterations(self) -> None:
        for iterations in (0, -1, 1.5, True, "1000"):
            with self.subTest(iterations=iterations):
                with self.assertRaises(ValueError):
                    crypto.derive_key(PASSWORD, self.salt, iterations)  # type: ignore[arg-type]

    def test_rejects_invalid_salt(self) -> None:
        for salt in (bytes(15), bytes(32), "0123456789abcdef"):
            with self.subTest(salt=salt):
                with self.assertRaises(ValueError):
                    crypto.derive_key(PASSWORD, salt, FAST_ITERATIONS)  # type: ignore[arg-type]


class KeyCheckTest(CryptoTestCase):
    def test_correct_key_is_verified(self) -> None:
        key_check = crypto.make_key_check(self.key)
        self.assertIsInstance(key_check, str)
        crypto.verify_key(self.key, key_check)

    def test_each_verifier_is_different(self) -> None:
        self.assertNotEqual(crypto.make_key_check(self.key), crypto.make_key_check(self.key))

    def test_verifier_does_not_contain_the_constant_or_password(self) -> None:
        key_check = crypto.make_key_check(self.key)
        decoded = base64.urlsafe_b64decode(key_check)
        self.assertNotIn(crypto.KEY_CHECK_PLAINTEXT, decoded)
        self.assertNotIn(PASSWORD, key_check)

    def test_wrong_password_is_rejected(self) -> None:
        key_check = crypto.make_key_check(self.key)
        wrong_key = crypto.derive_key(WRONG_PASSWORD, self.salt, FAST_ITERATIONS)
        with self.assertRaises(AuthenticationError):
            crypto.verify_key(wrong_key, key_check)

    def test_token_with_other_plaintext_is_rejected(self) -> None:
        other = Fernet(self.key).encrypt(b"mi6:key-check:v2").decode("ascii")
        with self.assertRaises(AuthenticationError):
            crypto.verify_key(self.key, other)

    def test_every_flipped_byte_is_detected(self) -> None:
        key_check = crypto.make_key_check(self.key)
        size = len(base64.urlsafe_b64decode(key_check))
        for index in range(size):
            with self.subTest(byte=index):
                with self.assertRaises(AuthenticationError):
                    crypto.verify_key(self.key, flip_bit(key_check, index))

    def test_trailing_data_after_padding_is_rejected_on_every_python(self) -> None:
        key_check = crypto.make_key_check(self.key)
        self.assertTrue(key_check.endswith("="))
        token = crypto.encrypt_report(self.key, REPORT)
        for bad, check in ((key_check + "AAAA", crypto.verify_key), (token + "AAAA", crypto.decrypt_report),
                           (key_check + "=", crypto.verify_key), (" " + token, crypto.decrypt_report)):
            with self.subTest(suffix=bad[-6:]):
                with self.assertRaises(AuthenticationError):
                    check(self.key, bad)

    def test_malformed_verifiers_are_rejected(self) -> None:
        key_check = crypto.make_key_check(self.key)
        for bad in ("", "garbage", key_check[:-8], key_check + "AAAA", "ñ" * 100):
            with self.subTest(bad=bad[:20]):
                with self.assertRaises(AuthenticationError):
                    crypto.verify_key(self.key, bad)


class ReportEncryptionTest(CryptoTestCase):
    def test_round_trip(self) -> None:
        token = crypto.encrypt_report(self.key, REPORT)
        self.assertIsInstance(token, str)
        self.assertEqual(crypto.decrypt_report(self.key, token), REPORT)

    def test_round_trip_preserves_layout_and_emoji_sequences(self) -> None:
        report = "Línea 1\nLínea 2\tfin 👨\u200d👩\u200d👧"
        self.assertEqual(crypto.decrypt_report(self.key, crypto.encrypt_report(self.key, report)), report)

    def test_same_report_gives_different_tokens(self) -> None:
        self.assertNotEqual(crypto.encrypt_report(self.key, REPORT), crypto.encrypt_report(self.key, REPORT))

    def test_token_does_not_reveal_the_report(self) -> None:
        token = crypto.encrypt_report(self.key, REPORT)
        decoded = base64.urlsafe_b64decode(token)
        self.assertNotIn(REPORT.encode("utf-8"), decoded)
        self.assertNotIn("Estambul", token)
        self.assertNotIn(b"Estambul", decoded)

    def test_wrong_key_is_rejected(self) -> None:
        token = crypto.encrypt_report(self.key, REPORT)
        wrong_key = crypto.derive_key(WRONG_PASSWORD, self.salt, FAST_ITERATIONS)
        with self.assertRaises(AuthenticationError):
            crypto.decrypt_report(wrong_key, token)

    def test_every_flipped_byte_is_detected(self) -> None:
        token = crypto.encrypt_report(self.key, REPORT)
        size = len(base64.urlsafe_b64decode(token))
        for index in range(size):
            with self.subTest(byte=index):
                with self.assertRaises(AuthenticationError):
                    crypto.decrypt_report(self.key, flip_bit(token, index))

    def test_truncated_or_extended_tokens_are_rejected(self) -> None:
        token = crypto.encrypt_report(self.key, REPORT)
        data = base64.urlsafe_b64decode(token)
        for bad in (data[:-1], data[:-32], data + b"\x00", data[:57]):
            with self.subTest(size=len(bad)):
                with self.assertRaises(AuthenticationError):
                    crypto.decrypt_report(self.key, base64.urlsafe_b64encode(bad).decode())

    def test_non_utf8_plaintext_is_rejected(self) -> None:
        token = Fernet(self.key).encrypt(b"\xff\xfe").decode("ascii")
        with self.assertRaises(AuthenticationError):
            crypto.decrypt_report(self.key, token)


class MandatoryDecryptionTest(MI6TestCase):
    """Spec, section 8, and plan, section 6.3: end to end through the stored file."""

    def setUp(self) -> None:
        super().setUp()
        operations.create_mission(
            self.data_dir, "007", "SKYFALL", "4", REPORT, PASSWORD, PASSWORD,
            kdf_iterations=FAST_ITERATIONS, now=self.now,
        )

    def stored_agent(self) -> dict:
        return json.loads(self.missions_file.read_text(encoding="utf-8"))["agents"]["007"]

    def key_from_file(self, password: str) -> bytes:
        kdf = self.stored_agent()["kdf"]
        return crypto.derive_key(password, crypto.decode_salt(kdf["salt"]), kdf["iterations"])

    def test_1_and_2_report_and_password_never_appear_in_clear(self) -> None:
        raw = self.missions_file.read_bytes()
        forbidden = [
            REPORT.encode("utf-8"),
            json.dumps(REPORT).encode("ascii"),
            "Estambul".encode("utf-8"),
            "Ñandú".encode("utf-8"),
            "\\u00d1and\\u00fa".encode("ascii"),
            PASSWORD.encode("utf-8"),
        ]
        for needle in forbidden:
            with self.subTest(needle=needle):
                self.assertNotIn(needle, raw)

    def test_3_correct_password_decrypts_normalized_report(self) -> None:
        agent = self.stored_agent()
        key = self.key_from_file(PASSWORD)
        crypto.verify_key(key, agent["key_check"])
        report = crypto.decrypt_report(key, agent["missions"][0]["report_token"])
        self.assertEqual(report, normalize_report(REPORT))

    def test_4_wrong_password_is_rejected(self) -> None:
        agent = self.stored_agent()
        key = self.key_from_file(WRONG_PASSWORD)
        with self.assertRaises(AuthenticationError):
            crypto.verify_key(key, agent["key_check"])
        with self.assertRaises(AuthenticationError):
            crypto.decrypt_report(key, agent["missions"][0]["report_token"])

    def test_5_tampered_token_is_detected(self) -> None:
        token = self.stored_agent()["missions"][0]["report_token"]
        middle = len(token) // 2
        replacement = "A" if token[middle] != "A" else "B"
        tampered = token[:middle] + replacement + token[middle + 1:]
        with self.assertRaises(AuthenticationError):
            crypto.decrypt_report(self.key_from_file(PASSWORD), tampered)

    def test_5_broken_token_format_is_reported_as_corrupt(self) -> None:
        document = json.loads(self.missions_file.read_text(encoding="utf-8"))
        token = document["agents"]["007"]["missions"][0]["report_token"]
        document["agents"]["007"]["missions"][0]["report_token"] = token[:40]
        self.missions_file.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(CorruptDataError) as ctx:
            operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(ctx.exception.reason, "invalid")

    def test_6_report_still_decrypts_after_archiving(self) -> None:
        token_before = self.stored_agent()["missions"][0]["report_token"]
        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        mission = self.stored_agent()["missions"][0]
        self.assertEqual(mission["status"], "archived")
        self.assertEqual(mission["report_token"], token_before)
        self.assertEqual(
            crypto.decrypt_report(self.key_from_file(PASSWORD), mission["report_token"]),
            normalize_report(REPORT),
        )
