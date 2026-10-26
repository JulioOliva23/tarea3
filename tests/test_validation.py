"""Tests for mi6.core.validation (RF-1.1, RF-2.3, RF-2.4, RF-3.5 to RF-3.9; spec, section 6)."""

from __future__ import annotations

import unittest
import unicodedata

from mi6.core import validation
from mi6.core.errors import InvalidAgentCodeError, PasswordPolicyError, ValidationError
from mi6.core.validation import (
    normalize_report,
    validate_agent_code,
    validate_code_name,
    validate_new_password,
    validate_threat_level,
)

ZWJ = "\u200d"
FAMILY_EMOJI = "\U0001F468\u200d\U0001F469\u200d\U0001F467"


class ConstantsTest(unittest.TestCase):
    def test_limits(self) -> None:
        self.assertEqual(validation.CODE_NAME_MAX_LENGTH, 30)
        self.assertEqual(validation.REPORT_MAX_LENGTH, 500)
        self.assertEqual(validation.PASSWORD_MIN_LENGTH, 8)


class ValidateAgentCodeTest(unittest.TestCase):
    def test_accepts_001_to_009(self) -> None:
        for number in range(1, 10):
            code = f"00{number}"
            with self.subTest(code=code):
                self.assertEqual(validate_agent_code(code), code)

    def test_strips_surrounding_whitespace(self) -> None:
        for raw, expected in [(" 007 ", "007"), ("\t005\n", "005"), (" 003　", "003")]:
            with self.subTest(raw=raw):
                self.assertEqual(validate_agent_code(raw), expected)

    def test_rejects_invalid_codes(self) -> None:
        cases = [
            "000", "0007", "07", "7", "00A", "００７", "", "   ",
            "010", "100", "0 07", "00١", "007\n008", "-007", "+007", "00 7", "007a",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidAgentCodeError) as ctx:
                    validate_agent_code(raw)
                self.assertEqual(ctx.exception.field, "agent_code")
                self.assertEqual(ctx.exception.rule, "format")

    def test_rejects_non_string(self) -> None:
        for raw in [7, None, b"007"]:
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidAgentCodeError):
                    validate_agent_code(raw)  # type: ignore[arg-type]


class ValidateThreatLevelTest(unittest.TestCase):
    def test_accepts_1_to_5_as_int(self) -> None:
        for level in range(1, 6):
            with self.subTest(level=level):
                result = validate_threat_level(str(level))
                self.assertEqual(result, level)
                self.assertIs(type(result), int)

    def test_strips_surrounding_whitespace(self) -> None:
        self.assertEqual(validate_threat_level(" 3 "), 3)
        self.assertEqual(validate_threat_level("\t4\n"), 4)

    def test_rejects_out_of_range_or_malformed(self) -> None:
        cases = [
            "0", "6", "9", "03", "+3", "3.0", "-1", "٣", "３", "tres",
            "", " ", "1 2", "12", "3\n3", "0x3", "³",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError) as ctx:
                    validate_threat_level(raw)
                self.assertEqual(ctx.exception.field, "threat_level")
                self.assertEqual(ctx.exception.rule, "range")

    def test_rejects_non_string(self) -> None:
        for raw in [3, 3.0, True, None]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError) as ctx:
                    validate_threat_level(raw)  # type: ignore[arg-type]
                self.assertEqual(ctx.exception.field, "threat_level")
                self.assertEqual(ctx.exception.rule, "type")


class ValidateCodeNameTest(unittest.TestCase):
    def test_accepts_and_uppercases(self) -> None:
        cases = {
            "skyfall": "SKYFALL",
            "SKYFALL": "SKYFALL",
            "SkyFall": "SKYFALL",
            "golden-eye-007": "GOLDEN-EYE-007",
            "A": "A",
            "-": "-",
            "a" * 30: "A" * 30,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(validate_code_name(raw), expected)

    def test_lower_and_upper_case_give_same_name(self) -> None:
        self.assertEqual(validate_code_name("skyfall"), validate_code_name("SKYFALL"))

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_code_name("")
        self.assertEqual((ctx.exception.field, ctx.exception.rule), ("code_name", "empty"))

    def test_rejects_too_long(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_code_name("A" * 31)
        self.assertEqual((ctx.exception.field, ctx.exception.rule), ("code_name", "length"))
        self.assertEqual(ctx.exception.length, 31)

    def test_rejects_forbidden_characters(self) -> None:
        cases = [
            "../x", "/", "SKY/FALL", "A B", " SKYFALL", "SKYFALL ", "ÁGUILA",
            "SКYFALL", "SKY\u200bFALL", "SKY\u200dFALL", "\x1b[2J", "SKYFALL\n",
            "sky_fall", "sky.fall", "K", "ı", "straße", "ＳKYFALL", "   ",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError) as ctx:
                    validate_code_name(raw)
                self.assertEqual(ctx.exception.field, "code_name")
                self.assertEqual(ctx.exception.rule, "chars")

    def test_rejects_non_string(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_code_name(None)  # type: ignore[arg-type]
        self.assertEqual((ctx.exception.field, ctx.exception.rule), ("code_name", "type"))


class NormalizeReportTest(unittest.TestCase):
    def assert_rejected(self, raw: object, rule: str) -> ValidationError:
        with self.assertRaises(ValidationError) as ctx:
            normalize_report(raw)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, "report")
        self.assertEqual(ctx.exception.rule, rule)
        return ctx.exception

    def test_accepts_spanish_text_emojis_and_layout(self) -> None:
        cases = [
            "Objetivo neutralizado en Estambul.",
            "Ñandú, pingüino y camión.",
            f"La familia {FAMILY_EMOJI} está a salvo.",
            "\U0001F9A9 avistado",
            "Línea 1\nLínea 2\n\nLínea 4",
            "Col1\tCol2",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_report(raw), raw)

    def test_converts_crlf_to_lf(self) -> None:
        self.assertEqual(normalize_report("uno\r\ndos\r\ntres"), "uno\ndos\ntres")

    def test_strips_ascii_and_unicode_whitespace(self) -> None:
        self.assertEqual(normalize_report("  \n\t informe  　\n"), "informe")

    def test_normalizes_to_nfc(self) -> None:
        decomposed = unicodedata.normalize("NFD", "Ñandú")
        self.assertNotEqual(decomposed, "Ñandú")
        self.assertEqual(normalize_report(decomposed), "Ñandú")

    def test_keeps_zwj_inside_emoji(self) -> None:
        result = normalize_report(FAMILY_EMOJI)
        self.assertEqual(result, FAMILY_EMOJI)
        self.assertEqual(result.count(ZWJ), 2)

    def test_zwj_only_report_is_accepted_per_current_spec(self) -> None:
        # RF-3.9 only rejects whitespace-only text; ZWJ is a Cf character, not
        # whitespace, and is explicitly allowed by the plan (section 4.2).
        self.assertEqual(normalize_report(ZWJ), ZWJ)
        self.assertEqual(normalize_report(f"  {ZWJ}{ZWJ}\n"), ZWJ + ZWJ)

    def test_length_limits(self) -> None:
        self.assertEqual(normalize_report("a"), "a")
        self.assertEqual(len(normalize_report("a" * 500)), 500)
        self.assertEqual(len(normalize_report("  " + "a" * 500 + "\n")), 500)
        error = self.assert_rejected("a" * 501, "length")
        self.assertEqual(error.length, 501)

    def test_length_is_counted_after_nfc(self) -> None:
        decomposed = unicodedata.normalize("NFD", "é") * 500
        self.assertEqual(len(decomposed), 1000)
        self.assertEqual(normalize_report(decomposed), "é" * 500)

    def test_composite_emoji_counts_every_code_point(self) -> None:
        self.assertEqual(len(FAMILY_EMOJI), 5)
        self.assertEqual(len(normalize_report("a" * 495 + FAMILY_EMOJI)), 500)
        self.assert_rejected("a" * 496 + FAMILY_EMOJI, "length")

    def test_rejects_empty_and_whitespace_only(self) -> None:
        for raw in ["", " ", "\n\t \r\n", " ", " 　 ", "  "]:
            with self.subTest(raw=raw):
                self.assert_rejected(raw, "empty")

    def test_rejects_forbidden_characters(self) -> None:
        cases = {
            "ansi escape": "x\x1b[2J",
            "nul": "a\x00b",
            "bell": "a\x07b",
            "delete": "a\x7fb",
            "lone carriage return": "a\rb",
            "c1 control": "a\x85b",
            "right-to-left override": "a\u202eb",
            "zero width space": "a\u200bb",
            "byte order mark": "\ufeffinforme",
            "zero width non-joiner": "a\u200cb",
            "lone surrogate": "a\ud800b",
            "private use": "ab",
            "unassigned": "a͸b",
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                self.assert_rejected(raw, "chars")

    def test_rejects_non_string(self) -> None:
        self.assert_rejected(b"informe", "encoding")
        self.assert_rejected(None, "encoding")


class ValidateNewPasswordTest(unittest.TestCase):
    def assert_policy(self, password: object, confirmation: object, rule: str) -> None:
        with self.assertRaises(PasswordPolicyError) as ctx:
            validate_new_password(password, confirmation)  # type: ignore[arg-type]
        self.assertIsInstance(ctx.exception, ValidationError)
        self.assertEqual(ctx.exception.field, "password")
        self.assertEqual(ctx.exception.rule, rule)

    def test_accepts_eight_or_more_matching_characters(self) -> None:
        for password in ["12345678", "clave-segura-1", "ñandú🦩🦩🦩", "x" * 200]:
            with self.subTest(password=password):
                self.assertEqual(validate_new_password(password, password), password)

    def test_rejects_seven_characters(self) -> None:
        self.assert_policy("1234567", "1234567", "too_short")
        self.assert_policy("", "", "too_short")

    def test_rejects_mismatch(self) -> None:
        self.assert_policy("clave-segura-1", "clave-segura-2", "mismatch")
        self.assert_policy("clave-segura-1", "clave-segura-1 ", "mismatch")

    def test_too_short_is_reported_before_mismatch(self) -> None:
        self.assert_policy("1234567", "7654321", "too_short")

    def test_nfc_and_nfd_are_the_same_password(self) -> None:
        nfc = "contraseña"
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(validate_new_password(nfd, nfc), nfc)
        self.assertEqual(validate_new_password(nfc, nfd), nfc)

    def test_length_is_counted_after_nfc(self) -> None:
        decomposed = unicodedata.normalize("NFD", "é") * 4
        self.assertEqual(len(decomposed), 8)
        self.assert_policy(decomposed, decomposed, "too_short")

    def test_rejects_non_string(self) -> None:
        self.assert_policy(None, "12345678", "mismatch")
        self.assert_policy("12345678", b"12345678", "mismatch")


if __name__ == "__main__":
    unittest.main()
