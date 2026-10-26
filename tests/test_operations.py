"""Tests for mi6.core.operations (RF-2 to RF-6; plan, section 4.4)."""

from __future__ import annotations

import fcntl
import inspect
import json
import os
from datetime import datetime, timedelta, timezone
from unittest import mock

from mi6.core import crypto, operations
from mi6.core.errors import (
    AuthenticationError,
    CorruptDataError,
    DataAccessError,
    DuplicateMissionError,
    InsecurePermissionsError,
    InvalidAgentCodeError,
    MissionNotFoundError,
    OperationInProgressError,
    PasswordPolicyError,
    SymlinkError,
    ValidationError,
)
from mi6.core.models import Mission, MissionStatus, RiskLevel, RiskReport
from tests.test_base import FAST_ITERATIONS, MI6TestCase, skip_if_root

PASSWORD = "clave-segura-1"
OTHER_PASSWORD = "otra-clave-006"
REPORT = "Objetivo localizado en Estambul."


class OperationsTestCase(MI6TestCase):
    def create(
        self,
        agent: str = "007",
        name: str = "SKYFALL",
        threat: str = "4",
        report: str = REPORT,
        password: str = PASSWORD,
        confirmation: str | None = PASSWORD,
        now: datetime | None = None,
    ) -> Mission:
        return operations.create_mission(
            self.data_dir, agent, name, threat, report, password, confirmation,
            kdf_iterations=FAST_ITERATIONS, now=self.now if now is None else now,
        )

    def stored(self) -> dict:
        return json.loads(self.missions_file.read_text(encoding="utf-8"))

    def names(self, report: RiskReport) -> list[str]:
        return [mission.code_name for mission in report.active_missions]


class CreateFirstMissionTest(OperationsTestCase):
    def test_creates_active_mission(self) -> None:
        mission = self.create(agent=" 007 ", name="skyfall", threat=" 4 ")
        self.assertEqual(mission.code_name, "SKYFALL")
        self.assertEqual(mission.threat_level, 4)
        self.assertIs(mission.status, MissionStatus.ACTIVE)
        self.assertEqual(mission.created_at, self.now)

    def test_first_use_creates_private_files(self) -> None:
        self.set_umask(0o000)
        self.create()
        self.assertEqual(self.mode_of(self.data_dir), 0o700)
        self.assertEqual(self.mode_of(self.missions_file), 0o600)
        self.assertEqual(self.mode_of(self.lock_file), 0o600)
        self.assertEqual(sorted(os.listdir(self.data_dir)), ["missions.json", "missions.lock"])

    def test_stored_document_layout(self) -> None:
        self.create()
        document = self.stored()
        self.assertEqual(document["schema_version"], 1)
        agent = document["agents"]["007"]
        self.assertEqual(agent["kdf"]["algorithm"], "pbkdf2_hmac_sha256")
        self.assertEqual(agent["kdf"]["iterations"], FAST_ITERATIONS)
        self.assertEqual(len(crypto.decode_salt(agent["kdf"]["salt"])), 16)
        self.assertEqual(
            agent["missions"],
            [{
                "code_name": "SKYFALL",
                "threat_level": 4,
                "status": "active",
                "created_at": "2026-10-26T14:32:07+01:00",
                "report_token": agent["missions"][0]["report_token"],
            }],
        )

    def test_report_is_encrypted_with_the_agent_password(self) -> None:
        self.create(report="  Ñandú 🦩\r\nen Estambul  ")
        raw = self.missions_file.read_bytes()
        self.assertNotIn("Estambul".encode(), raw)
        self.assertNotIn(PASSWORD.encode(), raw)
        agent = self.stored()["agents"]["007"]
        key = crypto.derive_key(PASSWORD, crypto.decode_salt(agent["kdf"]["salt"]), FAST_ITERATIONS)
        self.assertEqual(crypto.decrypt_report(key, agent["missions"][0]["report_token"]), "Ñandú 🦩\nen Estambul")

    def test_microseconds_are_dropped_and_offset_kept(self) -> None:
        mission = self.create(now=self.now.replace(microsecond=987654))
        self.assertEqual(mission.created_at.microsecond, 0)
        self.assertEqual(self.stored()["agents"]["007"]["missions"][0]["created_at"], "2026-10-26T14:32:07+01:00")

    def test_default_now_is_current_local_time(self) -> None:
        before = datetime.now().astimezone().replace(microsecond=0)
        mission = operations.create_mission(
            self.data_dir, "007", "SKYFALL", "4", REPORT, PASSWORD, PASSWORD, kdf_iterations=FAST_ITERATIONS,
        )
        after = datetime.now().astimezone()
        self.assertIsNotNone(mission.created_at.utcoffset())
        self.assertTrue(before <= mission.created_at <= after)

    def test_default_iterations_is_production_value(self) -> None:
        parameter = inspect.signature(operations.create_mission).parameters["kdf_iterations"]
        self.assertEqual(parameter.default, 600_000)
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)


class CreateRejectionsOnFirstUseTest(OperationsTestCase):
    """Nothing may be written to disk when the first registration is rejected."""

    def assert_nothing_created(self) -> None:
        self.assertFalse(self.data_dir.exists())

    def test_password_too_short(self) -> None:
        with self.assertRaises(PasswordPolicyError) as ctx:
            self.create(password="1234567", confirmation="1234567")
        self.assertEqual(ctx.exception.rule, "too_short")
        self.assert_nothing_created()

    def test_password_mismatch(self) -> None:
        with self.assertRaises(PasswordPolicyError) as ctx:
            self.create(confirmation="clave-segura-2")
        self.assertEqual(ctx.exception.rule, "mismatch")
        self.assert_nothing_created()

    def test_missing_confirmation_for_new_agent(self) -> None:
        with self.assertRaises(PasswordPolicyError) as ctx:
            self.create(confirmation=None)
        self.assertEqual(ctx.exception.rule, "mismatch")
        self.assert_nothing_created()

    def test_invalid_fields(self) -> None:
        cases = [
            ({"agent": "000"}, InvalidAgentCodeError, "agent_code"),
            ({"name": "../x"}, ValidationError, "code_name"),
            ({"threat": "6"}, ValidationError, "threat_level"),
            ({"report": "   "}, ValidationError, "report"),
            ({"report": "x" * 501}, ValidationError, "report"),
            ({"report": "x\x1b[2J"}, ValidationError, "report"),
        ]
        for kwargs, error, field in cases:
            with self.subTest(**kwargs):
                with self.assertRaises(error) as ctx:
                    self.create(**kwargs)
                self.assertEqual(ctx.exception.field, field)
                self.assert_nothing_created()

    def test_naive_now_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.create(now=datetime(2026, 10, 26, 14, 32))
        self.assert_nothing_created()

    def test_invalid_iterations_are_rejected(self) -> None:
        for iterations in (0, -1, True):
            with self.subTest(iterations=iterations):
                with self.assertRaises(ValueError):
                    operations.create_mission(
                        self.data_dir, "007", "SKYFALL", "4", REPORT, PASSWORD, PASSWORD,
                        kdf_iterations=iterations, now=self.now,
                    )
                self.assert_nothing_created()

    def test_interrupted_first_registration_leaves_no_remnants(self) -> None:
        with mock.patch("mi6.core.operations.crypto.encrypt_report", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.create()
        self.assert_nothing_created()

    def test_failed_first_write_leaves_no_remnants(self) -> None:
        with mock.patch("mi6.core.storage.os.replace", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(DataAccessError):
                self.create()
        self.assert_nothing_created()


class CreateExistingAgentTest(OperationsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create()
        self.before = self.snapshot_dir()

    def assert_unchanged(self) -> None:
        self.assertEqual(self.snapshot_dir(), self.before)

    def test_second_mission_needs_only_the_password(self) -> None:
        self.create(name="GOLDENEYE", threat="3", confirmation=None, now=self.now + timedelta(hours=1))
        missions = self.stored()["agents"]["007"]["missions"]
        self.assertEqual([m["code_name"] for m in missions], ["SKYFALL", "GOLDENEYE"])

    def test_agent_keeps_salt_and_verifier(self) -> None:
        agent_before = self.stored()["agents"]["007"]
        self.create(name="GOLDENEYE")
        agent_after = self.stored()["agents"]["007"]
        self.assertEqual(agent_after["kdf"], agent_before["kdf"])
        self.assertEqual(agent_after["key_check"], agent_before["key_check"])

    def test_confirmation_is_ignored_for_existing_agent(self) -> None:
        self.create(name="GOLDENEYE", confirmation="anything-else")
        self.assertEqual(len(self.stored()["agents"]["007"]["missions"]), 2)

    def test_wrong_password_changes_nothing(self) -> None:
        with self.assertRaises(AuthenticationError):
            self.create(name="GOLDENEYE", password="clave-segura-2", confirmation=None)
        self.assert_unchanged()

    def test_duplicate_active_mission(self) -> None:
        for name in ("SKYFALL", "skyfall", "SkyFall"):
            with self.subTest(name=name):
                with self.assertRaises(DuplicateMissionError) as ctx:
                    self.create(name=name)
                self.assertEqual(ctx.exception.code_name, "SKYFALL")
                self.assertEqual(ctx.exception.status, MissionStatus.ACTIVE)
                self.assert_unchanged()

    def test_duplicate_archived_mission(self) -> None:
        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        before = self.snapshot_dir()
        with self.assertRaises(DuplicateMissionError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.status, "archived")
        self.assertEqual(self.snapshot_dir(), before)

    def test_duplicate_is_rejected_before_checking_password(self) -> None:
        with self.assertRaises(DuplicateMissionError):
            self.create(password="clave-segura-2")

    def test_same_code_name_for_another_agent(self) -> None:
        self.create(agent="006", threat="2", password=OTHER_PASSWORD, confirmation=OTHER_PASSWORD)
        agents = self.stored()["agents"]
        self.assertEqual(list(agents), ["007", "006"])
        self.assertNotEqual(agents["007"]["kdf"]["salt"], agents["006"]["kdf"]["salt"])
        self.assertEqual(agents["006"]["missions"][0]["threat_level"], 2)

    def test_new_agent_in_existing_data_still_needs_valid_password(self) -> None:
        with self.assertRaises(PasswordPolicyError):
            self.create(agent="006", password="corta", confirmation="corta")
        self.assert_unchanged()

    def test_failed_write_changes_nothing(self) -> None:
        for error in (OSError(28, "No space left on device"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with mock.patch("mi6.core.storage.os.replace", side_effect=error):
                    with self.assertRaises((DataAccessError, KeyboardInterrupt)):
                        self.create(name="GOLDENEYE")
                self.assert_unchanged()

    def test_lock_contention_changes_nothing(self) -> None:
        for held in (fcntl.LOCK_EX, fcntl.LOCK_SH):
            with self.subTest(held=held):
                fd = os.open(self.lock_file, os.O_RDWR)
                try:
                    fcntl.flock(fd, held | fcntl.LOCK_NB)
                    with self.assertRaises(OperationInProgressError):
                        self.create(name="GOLDENEYE")
                finally:
                    os.close(fd)
                self.assert_unchanged()

    def test_corrupt_data_is_never_overwritten(self) -> None:
        self.missions_file.write_text("{broken", encoding="utf-8")
        before = self.snapshot_dir()
        with self.assertRaises(CorruptDataError):
            self.create(name="GOLDENEYE")
        self.assertEqual(self.snapshot_dir(), before)


class PreflightCreateTest(OperationsTestCase):
    def test_returns_cleaned_fields_without_data(self) -> None:
        self.assertEqual(
            operations.preflight_create(self.data_dir, " 007 ", "skyfall", " 4 "),
            ("007", "SKYFALL", 4),
        )
        self.assertFalse(self.data_dir.exists())

    def test_validates_fields(self) -> None:
        cases = [("07", "SKYFALL", "4"), ("007", "SKY FALL", "4"), ("007", "SKYFALL", "+3")]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValidationError):
                    operations.preflight_create(self.data_dir, *args)

    def test_detects_duplicates_without_writing(self) -> None:
        self.create()
        self.create(name="SPECTRE", threat="5")
        operations.archive_mission(self.data_dir, "007", "SPECTRE", PASSWORD)
        before = self.snapshot_dir()
        mtime = os.stat(self.missions_file).st_mtime_ns
        for name, status in (("SKYFALL", "active"), ("spectre", "archived")):
            with self.subTest(name=name):
                with self.assertRaises(DuplicateMissionError) as ctx:
                    operations.preflight_create(self.data_dir, "007", name, "3")
                self.assertEqual(ctx.exception.status, status)
        self.assertEqual(operations.preflight_create(self.data_dir, "005", "SKYFALL", "3"), ("005", "SKYFALL", 3))
        self.assertEqual(self.snapshot_dir(), before)
        self.assertEqual(os.stat(self.missions_file).st_mtime_ns, mtime)

    def test_never_derives_keys(self) -> None:
        self.create()
        with mock.patch("mi6.core.operations.crypto.derive_key", side_effect=AssertionError("no password needed")):
            operations.preflight_create(self.data_dir, "007", "GOLDENEYE", "3")


class AgentExistsTest(OperationsTestCase):
    def test_without_data(self) -> None:
        self.assertFalse(operations.agent_exists(self.data_dir, "007"))
        self.assertFalse(self.data_dir.exists())

    def test_after_first_mission(self) -> None:
        self.create()
        self.assertTrue(operations.agent_exists(self.data_dir, " 007 "))
        self.assertFalse(operations.agent_exists(self.data_dir, "006"))

    def test_invalid_code(self) -> None:
        with self.assertRaises(InvalidAgentCodeError):
            operations.agent_exists(self.data_dir, "0007")


class ListActiveMissionsTest(OperationsTestCase):
    def test_without_data_is_empty_low_and_creates_nothing(self) -> None:
        report = operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(report, RiskReport(active_missions=(), total=0, level=RiskLevel.LOW))
        self.assertFalse(self.data_dir.exists())

    def test_agent_without_missions(self) -> None:
        self.create()
        report = operations.list_active_missions(self.data_dir, "006")
        self.assertEqual((report.active_missions, report.total, report.level), ((), 0, RiskLevel.LOW))

    def test_lists_active_missions_and_risk(self) -> None:
        self.create(name="SKYFALL", threat="4")
        self.create(name="SPECTRE", threat="5", now=self.now + timedelta(days=1))
        self.create(name="GOLDENEYE", threat="3", now=self.now + timedelta(days=2))
        self.create(agent="006", name="SKYFALL", threat="5", password=OTHER_PASSWORD, confirmation=OTHER_PASSWORD)
        operations.archive_mission(self.data_dir, "007", "SPECTRE", PASSWORD)
        report = operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(self.names(report), ["SKYFALL", "GOLDENEYE"])
        self.assertEqual((report.total, report.level), (7, RiskLevel.MEDIUM))

    def test_critical_risk(self) -> None:
        for index, threat in enumerate(("5", "5", "1")):
            self.create(name=f"OP-{index}", threat=threat)
        report = operations.list_active_missions(self.data_dir, "007")
        self.assertEqual((report.total, report.level), (11, RiskLevel.CRITICAL))

    def test_same_minute_keeps_registration_order(self) -> None:
        for name in ("ZULU", "ALPHA", "MIKE"):
            self.create(name=name, threat="1")
        self.assertEqual(self.names(operations.list_active_missions(self.data_dir, "007")), ["ZULU", "ALPHA", "MIKE"])

    def test_clock_skew_and_timezone_changes_do_not_change_order(self) -> None:
        self.create(name="FIRST", threat="1")
        self.create(name="AHEAD", threat="1", now=self.now + timedelta(days=365))
        self.create(name="BEHIND", threat="1", now=self.now - timedelta(days=30))
        self.create(name="OTHER-TZ", threat="1", now=self.now.astimezone(timezone(timedelta(hours=-5))))
        self.assertEqual(
            self.names(operations.list_active_missions(self.data_dir, "007")),
            ["FIRST", "AHEAD", "BEHIND", "OTHER-TZ"],
        )

    def test_needs_no_password_and_decrypts_nothing(self) -> None:
        self.create()
        forbidden = AssertionError("list must not touch cryptography")
        with mock.patch("mi6.core.operations.crypto.derive_key", side_effect=forbidden), \
                mock.patch("mi6.core.operations.crypto.decrypt_report", side_effect=forbidden), \
                mock.patch("mi6.core.operations.crypto.verify_key", side_effect=forbidden):
            report = operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(self.names(report), ["SKYFALL"])
        self.assertNotIn("password", inspect.signature(operations.list_active_missions).parameters)

    def test_does_not_write(self) -> None:
        self.create()
        before = self.snapshot_dir()
        with mock.patch("mi6.core.storage.write_document_atomic", side_effect=AssertionError("no writes")):
            operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(self.snapshot_dir(), before)

    def test_works_while_another_reader_holds_the_lock(self) -> None:
        self.create()
        self.hold_lock(fcntl.LOCK_SH)
        self.assertEqual(self.names(operations.list_active_missions(self.data_dir, "007")), ["SKYFALL"])

    def test_writer_in_progress(self) -> None:
        self.create()
        self.hold_lock(fcntl.LOCK_EX)
        with self.assertRaises(OperationInProgressError):
            operations.list_active_missions(self.data_dir, "007")

    def test_invalid_agent_code(self) -> None:
        with self.assertRaises(InvalidAgentCodeError):
            operations.list_active_missions(self.data_dir, "00A")


class DataProblemsTest(OperationsTestCase):
    """RF-6: every operation refuses unsafe or damaged data and leaves it as it is."""

    def operations_to_try(self):
        return {
            "list": lambda: operations.list_active_missions(self.data_dir, "007"),
            "preflight": lambda: operations.preflight_create(self.data_dir, "007", "GOLDENEYE", "3"),
            "get": lambda: operations.get_active_mission(self.data_dir, "007", "SKYFALL"),
            "create": lambda: self.create(name="GOLDENEYE"),
            "archive": lambda: operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD),
        }

    def assert_all_fail(self, error: type[Exception], reason: str | None = None) -> None:
        before = self.snapshot_dir()
        for name, run in self.operations_to_try().items():
            with self.subTest(operation=name):
                with self.assertRaises(error) as ctx:
                    run()
                if reason is not None:
                    self.assertEqual(ctx.exception.reason, reason)
                self.assertEqual(self.snapshot_dir(), before)

    def test_unparseable_json(self) -> None:
        self.create()
        self.missions_file.write_text("{oops", encoding="utf-8")
        self.assert_all_fail(CorruptDataError, "unreadable")

    def test_hand_edited_invalid_record(self) -> None:
        self.create()
        document = self.stored()
        document["agents"]["007"]["missions"][0]["threat_level"] = 9
        self.missions_file.write_text(json.dumps(document), encoding="utf-8")
        self.assert_all_fail(CorruptDataError, "invalid")

    def test_unknown_schema_version(self) -> None:
        self.create()
        document = self.stored()
        document["schema_version"] = 2
        self.missions_file.write_text(json.dumps(document), encoding="utf-8")
        self.assert_all_fail(CorruptDataError, "invalid")

    def test_orphan_temporary_file(self) -> None:
        self.create()
        (self.data_dir / ".missions.json.tmp-x1y2z3").write_text("{")
        self.assert_all_fail(CorruptDataError, "incomplete")

    def test_directory_without_files(self) -> None:
        self.data_dir.mkdir(mode=0o700)
        self.assert_all_fail(CorruptDataError, "incomplete")
        self.assertEqual(os.listdir(self.data_dir), [])

    def test_directory_without_missions_file(self) -> None:
        self.create()
        self.missions_file.unlink()
        self.assert_all_fail(CorruptDataError, "incomplete")

    @skip_if_root
    def test_open_permissions(self) -> None:
        for target, mode in ((self.missions_file, 0o644), (self.lock_file, 0o640), (self.data_dir, 0o755)):
            with self.subTest(target=target.name):
                if not self.data_dir.exists():
                    self.create()
                os.chmod(target, mode)
                self.assert_all_fail(InsecurePermissionsError)
                self.assertEqual(self.mode_of(target), mode)
                os.chmod(target, 0o700 if target == self.data_dir else 0o600)

    def test_symlinked_data_dir(self) -> None:
        real = self.tmp_path / "real-mi6"
        self.create()
        os.replace(self.data_dir, real)
        os.symlink(real, self.data_dir)
        self.assert_all_fail(SymlinkError)

    def test_symlinked_missions_file(self) -> None:
        self.create()
        elsewhere = self.tmp_path / "elsewhere.json"
        os.replace(self.missions_file, elsewhere)
        os.symlink(elsewhere, self.missions_file)
        self.assert_all_fail(SymlinkError)


class GetActiveMissionTest(OperationsTestCase):
    def test_returns_active_mission_without_password(self) -> None:
        self.create()
        with mock.patch("mi6.core.operations.crypto.derive_key", side_effect=AssertionError("no password")):
            mission = operations.get_active_mission(self.data_dir, "007", "skyfall")
        self.assertEqual((mission.code_name, mission.threat_level), ("SKYFALL", 4))

    def test_not_found_cases(self) -> None:
        self.create()
        self.create(name="SPECTRE", threat="5")
        operations.archive_mission(self.data_dir, "007", "SPECTRE", PASSWORD)
        for agent, name in (("007", "MOONRAKER"), ("007", "SPECTRE"), ("006", "SKYFALL")):
            with self.subTest(agent=agent, name=name):
                with self.assertRaises(MissionNotFoundError) as ctx:
                    operations.get_active_mission(self.data_dir, agent, name)
                self.assertEqual(ctx.exception.code_name, name)

    def test_without_data(self) -> None:
        with self.assertRaises(MissionNotFoundError):
            operations.get_active_mission(self.data_dir, "007", "SKYFALL")
        self.assertFalse(self.data_dir.exists())

    def test_invalid_fields(self) -> None:
        with self.assertRaises(InvalidAgentCodeError):
            operations.get_active_mission(self.data_dir, "7", "SKYFALL")
        with self.assertRaises(ValidationError):
            operations.get_active_mission(self.data_dir, "007", "SKY/FALL")


class ArchiveMissionTest(OperationsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create(name="SKYFALL", threat="4")
        self.create(name="GOLDENEYE", threat="3", now=self.now + timedelta(minutes=5))
        self.before = self.snapshot_dir()

    def assert_unchanged(self) -> None:
        self.assertEqual(self.snapshot_dir(), self.before)

    def test_archives_and_keeps_report_untouched(self) -> None:
        mission_before = self.stored()["agents"]["007"]["missions"][0]
        archived = operations.archive_mission(self.data_dir, " 007 ", "skyfall", PASSWORD)
        self.assertIs(archived.status, MissionStatus.ARCHIVED)
        self.assertEqual(archived.code_name, "SKYFALL")
        mission_after = self.stored()["agents"]["007"]["missions"][0]
        self.assertEqual(mission_after, {**mission_before, "status": "archived"})

    def test_archived_mission_leaves_listing_and_risk(self) -> None:
        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        report = operations.list_active_missions(self.data_dir, "007")
        self.assertEqual(self.names(report), ["GOLDENEYE"])
        self.assertEqual((report.total, report.level), (3, RiskLevel.LOW))

    def test_other_missions_and_agents_are_untouched(self) -> None:
        self.create(agent="006", password=OTHER_PASSWORD, confirmation=OTHER_PASSWORD)
        before = self.stored()
        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        after = self.stored()
        self.assertEqual(after["agents"]["006"], before["agents"]["006"])
        self.assertEqual(after["agents"]["007"]["missions"][1], before["agents"]["007"]["missions"][1])
        self.assertEqual(after["agents"]["007"]["key_check"], before["agents"]["007"]["key_check"])
        self.assertEqual(list(after["agents"]), ["007", "006"])

    def test_archiving_twice_is_not_found(self) -> None:
        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        before = self.snapshot_dir()
        with self.assertRaises(MissionNotFoundError):
            operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        self.assertEqual(self.snapshot_dir(), before)

    def test_unknown_mission_or_agent(self) -> None:
        for agent, name in (("007", "MOONRAKER"), ("006", "SKYFALL")):
            with self.subTest(agent=agent, name=name):
                with self.assertRaises(MissionNotFoundError):
                    operations.archive_mission(self.data_dir, agent, name, PASSWORD)
                self.assert_unchanged()

    def test_without_data(self) -> None:
        for child in self.data_dir.iterdir():
            child.unlink()
        self.data_dir.rmdir()
        with self.assertRaises(MissionNotFoundError):
            operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        self.assertFalse(self.data_dir.exists())

    def test_wrong_password_changes_nothing(self) -> None:
        for password in ("clave-segura-2", "", OTHER_PASSWORD):
            with self.subTest(password=password):
                with self.assertRaises(AuthenticationError):
                    operations.archive_mission(self.data_dir, "007", "SKYFALL", password)
                self.assert_unchanged()

    def test_failed_write_keeps_mission_active(self) -> None:
        for error in (OSError(13, "Permission denied"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with mock.patch("mi6.core.storage.os.replace", side_effect=error):
                    with self.assertRaises((DataAccessError, KeyboardInterrupt)):
                        operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
                self.assert_unchanged()
                self.assertEqual(self.names(operations.list_active_missions(self.data_dir, "007")),
                                 ["SKYFALL", "GOLDENEYE"])

    def test_lock_contention_changes_nothing(self) -> None:
        self.hold_lock(fcntl.LOCK_SH)
        with self.assertRaises(OperationInProgressError):
            operations.archive_mission(self.data_dir, "007", "SKYFALL", PASSWORD)
        self.assert_unchanged()

    def test_invalid_fields(self) -> None:
        with self.assertRaises(InvalidAgentCodeError):
            operations.archive_mission(self.data_dir, "000", "SKYFALL", PASSWORD)
        with self.assertRaises(ValidationError):
            operations.archive_mission(self.data_dir, "007", "", PASSWORD)
        self.assert_unchanged()
