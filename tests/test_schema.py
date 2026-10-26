"""Tests for mi6.core.schema (RF-6.4, RF-6.5; plan, section 2.3)."""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from cryptography.fernet import Fernet

from mi6.core.errors import CorruptDataError
from mi6.core.models import MissionsDocument, MissionStatus
from mi6.core.schema import is_fernet_token, parse_document
from tests.test_base import MI6TestCase

_FERNET = Fernet(Fernet.generate_key())


def token(payload: bytes = b"report") -> str:
    return _FERNET.encrypt(payload).decode("ascii")


def mission(code_name: str, threat: int = 3, status: str = "active") -> dict[str, Any]:
    return {
        "code_name": code_name,
        "threat_level": threat,
        "status": status,
        "created_at": "2026-10-20T09:15:42+01:00",
        "report_token": token(),
    }


def valid_raw() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "agents": {
            "007": {
                "kdf": {
                    "algorithm": "pbkdf2_hmac_sha256",
                    "iterations": 600000,
                    "salt": "q3Jx9mW2bT8vYp1LzK0aNg==",
                },
                "key_check": token(b"mi6:key-check:v1"),
                "missions": [
                    mission("SKYFALL", 4),
                    mission("SPECTRE", 5, "archived"),
                    mission("GOLDENEYE", 3),
                ],
            },
            "006": {
                "kdf": {
                    "algorithm": "pbkdf2_hmac_sha256",
                    "iterations": 600000,
                    "salt": "Zt4Hc1oPq8sWv0mN2xRyJA==",
                },
                "key_check": token(b"mi6:key-check:v1"),
                "missions": [mission("SKYFALL", 2)],
            },
        },
    }


def with_change(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    raw = copy.deepcopy(valid_raw())
    change(raw)
    return raw


def agent(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["agents"]["007"]


def first_mission(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["agents"]["007"]["missions"][0]


def set_version_byte(value: str, version: int) -> str:
    data = bytearray(base64.urlsafe_b64decode(value))
    data[0] = version
    return base64.urlsafe_b64encode(bytes(data)).decode("ascii")


class ParseValidDocumentTest(MI6TestCase):
    def test_plan_example_is_accepted(self) -> None:
        raw = valid_raw()
        document = parse_document(raw)
        self.assertIsInstance(document, MissionsDocument)
        self.assertEqual(list(document.agents), ["007", "006"])
        record = document.agents["007"]
        self.assertEqual(record.kdf.iterations, 600000)
        self.assertEqual(record.kdf.salt, "q3Jx9mW2bT8vYp1LzK0aNg==")
        self.assertEqual([m.code_name for m in record.missions], ["SKYFALL", "SPECTRE", "GOLDENEYE"])
        self.assertIs(record.missions[1].status, MissionStatus.ARCHIVED)
        self.assertEqual(record.missions[0].created_at, datetime(2026, 10, 20, 9, 15, 42, tzinfo=timezone(timedelta(hours=1))))
        self.assertEqual(document.agents["006"].missions[0].threat_level, 2)

    def test_round_trip_through_to_dict(self) -> None:
        raw = valid_raw()
        self.assertEqual(parse_document(raw).to_dict(), raw)

    def test_empty_agents_and_empty_missions(self) -> None:
        self.assertEqual(parse_document({"schema_version": 1, "agents": {}}), MissionsDocument())
        raw = with_change(lambda r: agent(r).__setitem__("missions", []))
        self.assertEqual(parse_document(raw).agents["007"].missions, ())

    def test_various_timezones_are_accepted(self) -> None:
        for value in ("2026-10-26T14:32:07+00:00", "2026-10-26T14:32:07Z", "2026-10-26T14:32:07.123456-05:30"):
            with self.subTest(created_at=value):
                raw = with_change(lambda r: first_mission(r).__setitem__("created_at", value))
                self.assertIsNotNone(parse_document(raw).agents["007"].missions[0].created_at.utcoffset())

    def test_same_code_name_in_two_agents_is_valid(self) -> None:
        document = parse_document(valid_raw())
        self.assertIsNotNone(document.agents["007"].find_mission("SKYFALL"))
        self.assertIsNotNone(document.agents["006"].find_mission("SKYFALL"))


class ParseInvalidDocumentTest(MI6TestCase):
    def assert_corrupt(self, raw: Any) -> CorruptDataError:
        with self.assertRaises(CorruptDataError) as ctx:
            parse_document(raw)
        self.assertEqual(ctx.exception.reason, "invalid")
        return ctx.exception

    def test_path_is_attached_to_the_error(self) -> None:
        with self.assertRaises(CorruptDataError) as ctx:
            parse_document([], path=self.missions_file)
        self.assertEqual(ctx.exception.path, self.missions_file)

    def test_top_level(self) -> None:
        cases: dict[str, Any] = {
            "list": [],
            "string": "{}",
            "null": None,
            "version 2": with_change(lambda r: r.__setitem__("schema_version", 2)),
            "version 0": with_change(lambda r: r.__setitem__("schema_version", 0)),
            "version as string": with_change(lambda r: r.__setitem__("schema_version", "1")),
            "version as bool": with_change(lambda r: r.__setitem__("schema_version", True)),
            "version as float": with_change(lambda r: r.__setitem__("schema_version", 1.0)),
            "missing version": with_change(lambda r: r.pop("schema_version")),
            "missing agents": with_change(lambda r: r.pop("agents")),
            "extra key": with_change(lambda r: r.__setitem__("extra", 1)),
            "agents as list": with_change(lambda r: r.__setitem__("agents", [])),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                self.assert_corrupt(raw)

    def test_agent_codes(self) -> None:
        for code in ("010", "000", "7", "07", "0007", " 007", "00A", "００７"):
            with self.subTest(code=code):
                self.assert_corrupt(with_change(lambda r: r["agents"].__setitem__(code, r["agents"].pop("007"))))

    def test_agent_record(self) -> None:
        cases = {
            "not an object": lambda r: r["agents"].__setitem__("007", []),
            "extra key": lambda r: agent(r).__setitem__("password", "x"),
            "missing kdf": lambda r: agent(r).pop("kdf"),
            "missing key_check": lambda r: agent(r).pop("key_check"),
            "missing missions": lambda r: agent(r).pop("missions"),
            "missions not a list": lambda r: agent(r).__setitem__("missions", {}),
            "key_check not fernet": lambda r: agent(r).__setitem__("key_check", "abc"),
            "key_check truncated": lambda r: agent(r).__setitem__("key_check", agent(r)["key_check"][:60]),
            "key_check wrong version": lambda r: agent(r).__setitem__(
                "key_check", set_version_byte(agent(r)["key_check"], 0x81)),
            "key_check not a string": lambda r: agent(r).__setitem__("key_check", 123),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assert_corrupt(with_change(change))

    def test_kdf(self) -> None:
        kdf = lambda r: agent(r)["kdf"]  # noqa: E731
        cases = {
            "not an object": lambda r: agent(r).__setitem__("kdf", "pbkdf2"),
            "extra key": lambda r: kdf(r).__setitem__("dklen", 32),
            "missing salt": lambda r: kdf(r).pop("salt"),
            "algorithm sha1": lambda r: kdf(r).__setitem__("algorithm", "pbkdf2_hmac_sha1"),
            "iterations 0": lambda r: kdf(r).__setitem__("iterations", 0),
            "iterations negative": lambda r: kdf(r).__setitem__("iterations", -5),
            "iterations bool": lambda r: kdf(r).__setitem__("iterations", True),
            "iterations string": lambda r: kdf(r).__setitem__("iterations", "600000"),
            "iterations float": lambda r: kdf(r).__setitem__("iterations", 600000.0),
            "salt 15 bytes": lambda r: kdf(r).__setitem__("salt", base64.b64encode(bytes(15)).decode()),
            "salt 17 bytes": lambda r: kdf(r).__setitem__("salt", base64.b64encode(bytes(17)).decode()),
            "salt not base64": lambda r: kdf(r).__setitem__("salt", "not-base64-at-all!!!!!!="),
            "salt url-safe alphabet": lambda r: kdf(r).__setitem__(
                "salt", base64.urlsafe_b64encode(b"\xfb" * 16).decode()),
            "salt not a string": lambda r: kdf(r).__setitem__("salt", 16),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assert_corrupt(with_change(change))

    def test_missions(self) -> None:
        m = first_mission
        cases = {
            "not an object": lambda r: agent(r)["missions"].__setitem__(0, "SKYFALL"),
            "extra key": lambda r: m(r).__setitem__("report", "en claro"),
            "missing status": lambda r: m(r).pop("status"),
            "code_name lowercase": lambda r: m(r).__setitem__("code_name", "skyfall"),
            "code_name too long": lambda r: m(r).__setitem__("code_name", "A" * 31),
            "code_name empty": lambda r: m(r).__setitem__("code_name", ""),
            "code_name with space": lambda r: m(r).__setitem__("code_name", "SKY FALL"),
            "code_name path": lambda r: m(r).__setitem__("code_name", "../X"),
            "code_name not a string": lambda r: m(r).__setitem__("code_name", 7),
            "threat true": lambda r: m(r).__setitem__("threat_level", True),
            "threat 0": lambda r: m(r).__setitem__("threat_level", 0),
            "threat 6": lambda r: m(r).__setitem__("threat_level", 6),
            "threat string": lambda r: m(r).__setitem__("threat_level", "3"),
            "threat float": lambda r: m(r).__setitem__("threat_level", 3.0),
            "status lost": lambda r: m(r).__setitem__("status", "lost"),
            "status in spanish": lambda r: m(r).__setitem__("status", "ACTIVA"),
            "status upper case": lambda r: m(r).__setitem__("status", "ACTIVE"),
            "status list": lambda r: m(r).__setitem__("status", ["active"]),
            "date without timezone": lambda r: m(r).__setitem__("created_at", "2026-10-20T09:15:42"),
            "date only": lambda r: m(r).__setitem__("created_at", "2026-10-20"),
            "date garbage": lambda r: m(r).__setitem__("created_at", "yesterday"),
            "date as number": lambda r: m(r).__setitem__("created_at", 1761000000),
            "token truncated": lambda r: m(r).__setitem__("report_token", m(r)["report_token"][:50]),
            "token plain text": lambda r: m(r).__setitem__("report_token", "Objetivo neutralizado"),
            "token standard alphabet": lambda r: m(r).__setitem__(
                "report_token", m(r)["report_token"][:-5] + "+" + m(r)["report_token"][-4:]),
            "token wrong version": lambda r: m(r).__setitem__(
                "report_token", set_version_byte(m(r)["report_token"], 0x00)),
            "duplicate code_name": lambda r: agent(r)["missions"].append(mission("SKYFALL", 1, "archived")),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assert_corrupt(with_change(change))


class IsFernetTokenTest(MI6TestCase):
    def test_real_tokens(self) -> None:
        for payload in (b"", b"x", b"x" * 16, "Ñandú 🦩".encode()):
            with self.subTest(size=len(payload)):
                self.assertTrue(is_fernet_token(token(payload)))

    def test_not_tokens(self) -> None:
        valid = token()
        data = base64.urlsafe_b64decode(valid)
        cases = [
            None, 123, b"gAAAAA", "", "gAAAAA", valid[:-4], valid + "AAAA",
            base64.urlsafe_b64encode(data[:72]).decode(),
            base64.urlsafe_b64encode(data + b"\x00").decode(),
            set_version_byte(valid, 0x81),
            "ñ" + valid[1:],
        ]
        for value in cases:
            with self.subTest(value=repr(value)[:30]):
                self.assertFalse(is_fernet_token(value))
