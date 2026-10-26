"""Tests for mi6.cli (RF-1.2, RF-2.1, RF-2.7, RF-3.1, RF-3.2, RF-4, RF-5, RF-7; plan, section 4)."""

from __future__ import annotations

import errno
import fcntl
import functools
import getpass
import inspect
import io
import json
import os
import string
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mi6.cli import main as cli_main
from mi6.cli import messages, prompts, render
from mi6.cli.main import build_parser, main
from mi6.cli.prompts import NoTerminalError
from mi6.core import operations, storage
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
    UnsafeEnvironmentError,
    ValidationError,
)
from mi6.core.models import Mission, MissionStatus, RiskLevel, RiskReport
from tests.test_base import FAST_ITERATIONS, MI6TestCase, skip_if_root

PASSWORD = "clave-segura-1"
REPORT = "Objetivo localizado en Estambul. Ñandú 🦩."
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class InteractiveStdin(io.StringIO):
    """A text stdin that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


class InterruptedStdin(io.StringIO):
    def read(self, *args: object) -> str:
        raise KeyboardInterrupt


class CliTestCase(MI6TestCase):
    def setUp(self) -> None:
        super().setUp()
        fast_create = functools.partial(operations.create_mission, kdf_iterations=FAST_ITERATIONS)
        patcher = mock.patch.object(operations, "create_mission", side_effect=fast_create)
        self.create_spy = patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(
        self,
        *argv: str,
        stdin: object = "",
        passwords: object = (),
        terminal: bool = True,
        data_dir: object = "default",
    ) -> SimpleNamespace:
        stdout, stderr = io.StringIO(), io.StringIO()
        stdin_stream = io.StringIO(stdin) if isinstance(stdin, str) else stdin
        side_effect = list(passwords) if isinstance(passwords, (list, tuple)) else passwords
        terminal_effect = None if terminal else NoTerminalError()
        with mock.patch("sys.stdin", stdin_stream), \
                mock.patch("mi6.cli.prompts.getpass.getpass", side_effect=side_effect) as getpass_mock, \
                mock.patch("mi6.cli.prompts.require_terminal", side_effect=terminal_effect), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            target = self.data_dir if data_dir == "default" else data_dir
            code = main(list(argv), data_dir=target)
        return SimpleNamespace(code=code, out=stdout.getvalue(), err=stderr.getvalue(), getpass=getpass_mock)

    def create(self, agent: str = "007", name: str = "SKYFALL", threat: str = "4",
               report: str = REPORT, passwords: object = (PASSWORD, PASSWORD)) -> SimpleNamespace:
        return self.run_cli("create", "-a", agent, "-n", name, "-t", threat, stdin=report, passwords=passwords)

    def snapshot(self) -> dict[str, bytes]:
        return self.snapshot_dir()


# --- Exit code 0 -------------------------------------------------------------


class HelpTest(CliTestCase):
    def test_explicit_help_exits_0_in_spanish(self) -> None:
        cases = [
            ["--help"], ["-h"], ["create", "--help"], ["list", "-h"], ["archive", "--help"],
            ["create", "-a", "007", "-h"], ["list", "--agent", "000", "--help"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                result = self.run_cli(*argv)
                self.assertEqual(result.code, 0)
                self.assertEqual(result.out, messages.HELP + "\n")
                self.assertEqual(result.err, "")
        self.assertFalse(self.data_dir.exists())

    def test_help_documents_commands_flags_and_safe_usage(self) -> None:
        for needle in ("create", "list", "archive", "--agent", "--code-name", "--threat", "--help",
                       "< informe.txt", "Ctrl+D", "historial"):
            with self.subTest(needle=needle):
                self.assertIn(needle, messages.HELP)
        self.assertNotIn("usage:", messages.HELP)
        self.assertNotIn("--report", messages.HELP)


class CreateCommandTest(CliTestCase):
    def test_piped_report_for_new_agent(self) -> None:
        result = self.create(agent=" 007 ", name="skyfall", threat=" 4 ")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(
            result.out,
            messages.CREATE_OK.format(code_name="SKYFALL", threat=4, agent="007") + "\n",
        )
        self.assertEqual(result.err, "")
        prompts_shown = [call.args[0] for call in result.getpass.call_args_list]
        self.assertEqual(prompts_shown, [messages.PASSWORD_NEW.format(agent="007"), messages.PASSWORD_REPEAT])
        mission = json.loads(self.missions_file.read_text())["agents"]["007"]["missions"][0]
        self.assertEqual((mission["code_name"], mission["threat_level"], mission["status"]), ("SKYFALL", 4, "active"))
        self.assertNotIn("Estambul".encode(), self.missions_file.read_bytes())

    def test_existing_agent_is_asked_once(self) -> None:
        self.create()
        result = self.create(name="GOLDENEYE", threat="3", passwords=[PASSWORD])
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual([c.args[0] for c in result.getpass.call_args_list], [messages.PASSWORD_PROMPT])

    def test_long_flags_and_name_alias(self) -> None:
        for flag in ("--code-name", "--name"):
            with self.subTest(flag=flag):
                result = self.run_cli("create", "--agent", "006", flag, f"OP{flag[2:6]}", "--threat", "2",
                                      stdin=REPORT, passwords=[PASSWORD] * 2)
                self.assertEqual(result.code, 0, result.err)

    def test_interactive_report_shows_prompt_on_stderr(self) -> None:
        result = self.run_cli("create", "-a", "007", "-n", "SKYFALL", "-t", "4",
                              stdin=InteractiveStdin("Línea 1\nLínea 2\n"), passwords=[PASSWORD] * 2)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.err, messages.REPORT_PROMPT + "\n")
        self.assertNotIn(messages.REPORT_PROMPT, result.out)

    def test_report_is_never_a_command_argument(self) -> None:
        result = self.run_cli("create", "-a", "007", "-n", "SKYFALL", "-t", "4", "--report", "texto")
        self.assertEqual(result.code, 2)
        self.assertFalse(self.data_dir.exists())

    def test_uses_production_iterations(self) -> None:
        self.create()
        self.assertNotIn("kdf_iterations", self.create_spy.call_args.kwargs)
        self.assertEqual(
            inspect.signature(operations.create_mission.side_effect.func).parameters["kdf_iterations"].default,
            600_000,
        )


class ListCommandTest(CliTestCase):
    def test_without_data(self) -> None:
        result = self.run_cli("list", "-a", "007")
        self.assertEqual(result.code, 0)
        self.assertEqual(
            result.out,
            messages.LIST_EMPTY.format(agent="007") + "\n"
            + messages.LIST_RISK.format(total=0, level="BAJO") + "\n",
        )
        self.assertFalse(self.data_dir.exists())

    def test_never_asks_for_password(self) -> None:
        self.create()
        self.create(name="GOLDENEYE", threat="3", passwords=[PASSWORD])
        result = self.run_cli("list", "--agent", " 007 ", passwords=AssertionError("no password"))
        self.assertEqual(result.code, 0, result.err)
        result.getpass.assert_not_called()
        self.assertIn(messages.LIST_HEADER.format(agent="007"), result.out)
        self.assertIn(messages.LIST_RISK.format(total=7, level="MEDIO"), result.out)
        self.assertLess(result.out.index("SKYFALL"), result.out.index("GOLDENEYE"))
        self.assertNotIn("Estambul", result.out)

    def test_critical_label_with_accent(self) -> None:
        for name, threat in (("A", "5"), ("B", "5"), ("C", "1")):
            self.create(name=name, threat=threat, passwords=[PASSWORD] * 2)
        result = self.run_cli("list", "-a", "007")
        self.assertIn("RIESGO GLOBAL: 11 · CRÍTICO", result.out)


class ArchiveCommandTest(CliTestCase):
    def test_preview_is_shown_before_password(self) -> None:
        self.create()
        stdout = io.StringIO()
        seen_before_prompt = []

        def fake_getpass(prompt: str) -> str:
            seen_before_prompt.append(stdout.getvalue())
            return PASSWORD

        with mock.patch("mi6.cli.prompts.getpass.getpass", side_effect=fake_getpass), \
                mock.patch("mi6.cli.prompts.require_terminal"), \
                redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["archive", "-a", "007", "-n", "skyfall"], data_dir=self.data_dir)
        self.assertEqual(code, 0)
        preview = messages.ARCHIVE_PREVIEW.format(code_name="SKYFALL", threat=4)
        self.assertEqual(seen_before_prompt, [preview + "\n"])
        self.assertEqual(stdout.getvalue(), preview + "\n" + messages.ARCHIVE_OK.format(code_name="SKYFALL") + "\n")

    def test_archived_mission_leaves_the_list(self) -> None:
        self.create()
        self.assertEqual(self.run_cli("archive", "-a", "007", "--code-name", "SKYFALL", passwords=[PASSWORD]).code, 0)
        result = self.run_cli("list", "-a", "007")
        self.assertIn(messages.LIST_EMPTY.format(agent="007"), result.out)


# --- Exit code 1 -------------------------------------------------------------


class RejectionTest(CliTestCase):
    def assert_rejected(self, result: SimpleNamespace, message: str) -> None:
        self.assertEqual(result.code, 1, result.err)
        self.assertEqual(result.err, message + "\n")
        self.assertEqual(result.out, "")

    def test_invalid_agent_code_is_access_denied(self) -> None:
        for code in ("000", "0007", "07", "00A", "００７", ""):
            for argv in (["list", "-a", code], ["create", "-a", code, "-n", "X", "-t", "1"],
                         ["archive", "-a", code, "-n", "X"]):
                with self.subTest(code=code, command=argv[0]):
                    self.assert_rejected(self.run_cli(*argv), messages.ERR_AGENT_CODE)
        self.assertFalse(self.data_dir.exists())

    def test_invalid_threat(self) -> None:
        for threat in ("0", "6", "03", "+3", "3.0", "-1", "٣", "tres"):
            with self.subTest(threat=threat):
                self.assert_rejected(self.create(threat=threat), messages.ERR_THREAT)
        self.assertFalse(self.data_dir.exists())

    def test_invalid_code_name(self) -> None:
        for name in ("../x", "/", "A B", "ÁGUILA", "SКYFALL", "SKY​FALL", "\x1b[2J", "A" * 31):
            with self.subTest(name=name):
                self.assert_rejected(self.create(name=name), messages.ERR_CODE_NAME)
        self.assertFalse(self.data_dir.exists())

    def test_invalid_report(self) -> None:
        cases = [
            ("", messages.ERR_REPORT_EMPTY),
            (" 　 \n", messages.ERR_REPORT_EMPTY),
            ("x\x1b[2J", messages.ERR_REPORT_CHARS),
            ("x‮y", messages.ERR_REPORT_CHARS),
            ("a" * 501, messages.ERR_REPORT_LENGTH.format(length=501)),
        ]
        for report, message in cases:
            with self.subTest(report=report[:10]):
                result = self.create(report=report)
                self.assert_rejected(result, message)
                result.getpass.assert_not_called()
        self.assertFalse(self.data_dir.exists())

    def test_non_utf8_report(self) -> None:
        stdin = io.TextIOWrapper(io.BytesIO(b"\xff\xfe informe"), encoding="utf-8")
        result = self.run_cli("create", "-a", "007", "-n", "SKYFALL", "-t", "4", stdin=stdin)
        self.assert_rejected(result, messages.ERR_REPORT_ENCODING)

    def test_new_password_policy(self) -> None:
        cases = [(("1234567", "1234567"), messages.ERR_PASSWORD_SHORT),
                 ((PASSWORD, "clave-segura-2"), messages.ERR_PASSWORD_MISMATCH)]
        for passwords, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(self.create(passwords=passwords), message)
        self.assertFalse(self.data_dir.exists())

    def test_wrong_password_changes_nothing(self) -> None:
        self.create()
        before = self.snapshot()
        self.assert_rejected(self.create(name="GOLDENEYE", passwords=["clave-segura-2"]), messages.ERR_AUTH)
        result = self.run_cli("archive", "-a", "007", "-n", "SKYFALL", passwords=["clave-segura-2"])
        self.assertEqual(result.code, 1)
        self.assertEqual(result.out, messages.ARCHIVE_PREVIEW.format(code_name="SKYFALL", threat=4) + "\n")
        self.assertEqual(result.err, messages.ERR_AUTH + "\n")
        self.assertEqual(self.snapshot(), before)

    def test_duplicates_are_rejected_before_reading_report_or_password(self) -> None:
        self.create()
        self.create(name="SPECTRE", threat="5", passwords=[PASSWORD])
        self.assertEqual(self.run_cli("archive", "-a", "007", "-n", "SPECTRE", passwords=[PASSWORD]).code, 0)
        before = self.snapshot()
        for name, status in (("skyfall", "activa"), ("SPECTRE", "archivada")):
            with self.subTest(name=name):
                stdin = InterruptedStdin()
                result = self.run_cli("create", "-a", "007", "-n", name, "-t", "1", stdin=stdin)
                self.assert_rejected(result, messages.ERR_DUPLICATE.format(code_name=name.upper(), status_es=status))
                result.getpass.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_archive_unknown_mission_never_asks_password(self) -> None:
        self.create()
        for name in ("MOONRAKER", "SKYFALL"):
            agent = "006" if name == "SKYFALL" else "007"
            with self.subTest(agent=agent, name=name):
                result = self.run_cli("archive", "-a", agent, "-n", name)
                self.assert_rejected(result, messages.ERR_NOT_FOUND.format(code_name=name))
                result.getpass.assert_not_called()

    def test_archive_twice(self) -> None:
        self.create()
        self.assertEqual(self.run_cli("archive", "-a", "007", "-n", "SKYFALL", passwords=[PASSWORD]).code, 0)
        self.assert_rejected(self.run_cli("archive", "-a", "007", "-n", "SKYFALL"),
                             messages.ERR_NOT_FOUND.format(code_name="SKYFALL"))


# --- Exit code 2 -------------------------------------------------------------


class UsageTest(CliTestCase):
    def test_bad_usage_shows_spanish_help_and_exits_2(self) -> None:
        cases = [
            [],
            ["delete", "-a", "007"],
            ["list"],
            ["list", "-a"],
            ["list", "-a", "007", "extra"],
            ["list", "-a", "007", "-n", "SKYFALL"],
            ["create", "-a", "007", "-n", "SKYFALL"],
            ["create", "-a", "007", "-t", "4"],
            ["create", "-a", "007", "-n", "SKYFALL", "-t", "4", "--report", "texto"],
            ["archive", "-a", "007"],
            ["archive", "-a", "007", "-n", "SKYFALL", "-t", "4"],
            ["list", "--ag", "007"],
            ["--version"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                result = self.run_cli(*argv)
                self.assertEqual(result.code, 2)
                self.assertEqual(result.out, "")
                self.assertEqual(result.err, messages.ERR_USAGE + "\n" + messages.HELP + "\n")
                self.assertNotIn("usage:", result.err)
        self.assertFalse(self.data_dir.exists())

    def test_no_terminal_on_create(self) -> None:
        result = self.run_cli("create", "-a", "007", "-n", "SKYFALL", "-t", "4",
                              stdin=InterruptedStdin(), terminal=False)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.err, messages.ERR_NO_TERMINAL + "\n")
        result.getpass.assert_not_called()
        self.assertFalse(self.data_dir.exists())

    def test_no_terminal_on_archive(self) -> None:
        self.create()
        before = self.snapshot()
        result = self.run_cli("archive", "-a", "007", "-n", "SKYFALL", terminal=False)
        self.assertEqual(result.code, 2)
        self.assertIn(messages.ERR_NO_TERMINAL, result.err)
        self.assertEqual(self.snapshot(), before)


# --- Exit code 3 -------------------------------------------------------------


class FailureTest(CliTestCase):
    def assert_failure(self, result: SimpleNamespace, message: str) -> None:
        self.assertEqual(result.code, 3, result.err)
        self.assertEqual(result.err, message + "\n")
        self.assertNotIn("Traceback", result.err)

    def test_corrupt_data(self) -> None:
        self.create()
        self.missions_file.write_text("{roto", encoding="utf-8")
        before = self.snapshot()
        expected = messages.ERR_CORRUPT.format(path=self.missions_file)
        self.assert_failure(self.run_cli("list", "-a", "007"), expected)
        self.assert_failure(self.create(name="GOLDENEYE", passwords=[PASSWORD]), expected)
        self.assertEqual(self.snapshot(), before)

    def test_remnants(self) -> None:
        self.data_dir.mkdir(mode=0o700)
        result = self.run_cli("list", "-a", "007")
        self.assert_failure(result, messages.ERR_CORRUPT.format(path=self.lock_file))

    @skip_if_root
    def test_insecure_permissions_tell_exact_chmod(self) -> None:
        self.create()
        os.chmod(self.missions_file, 0o644)
        result = self.run_cli("list", "-a", "007")
        self.assert_failure(
            result,
            messages.ERR_PERMISSIONS.format(path=self.missions_file, current="0644", expected="600"),
        )
        self.assertIn(f"chmod 600 {self.missions_file}", result.err)
        self.assertEqual(self.mode_of(self.missions_file), 0o644)
        os.chmod(self.missions_file, 0o600)
        os.chmod(self.data_dir, 0o755)
        self.assertIn(f"chmod 700 {self.data_dir}", self.run_cli("list", "-a", "007").err)

    def test_foreign_owner(self) -> None:
        error = InsecurePermissionsError(self.data_dir, 0o700, 0o700)
        with mock.patch.object(operations, "list_active_missions", side_effect=error):
            self.assert_failure(self.run_cli("list", "-a", "007"), messages.ERR_OWNER.format(path=self.data_dir))

    def test_symlink(self) -> None:
        real = self.tmp_path / "real"
        real.mkdir(mode=0o700)
        os.symlink(real, self.data_dir)
        self.assert_failure(self.run_cli("list", "-a", "007"), messages.ERR_SYMLINK.format(path=self.data_dir))

    def test_operation_in_progress(self) -> None:
        self.create()
        self.hold_lock(fcntl.LOCK_EX)
        self.assert_failure(self.run_cli("list", "-a", "007"), messages.ERR_IN_PROGRESS)

    def test_unsafe_environment(self) -> None:
        for reason, message in (("root", messages.ERR_ROOT), ("no_home", messages.ERR_NO_HOME)):
            with self.subTest(reason=reason):
                with mock.patch.object(storage, "resolve_data_dir", side_effect=UnsafeEnvironmentError(reason)):
                    self.assert_failure(self.run_cli("list", "-a", "007", data_dir=None), message)

    def test_real_root_check_through_resolve_data_dir(self) -> None:
        with mock.patch.object(storage, "resolve_data_dir", side_effect=self.unguarded_resolve_data_dir), \
                mock.patch("mi6.core.storage.os.geteuid", return_value=0):
            self.assert_failure(self.run_cli("list", "-a", "007", data_dir=None), messages.ERR_ROOT)

    def test_default_data_dir_is_resolved(self) -> None:
        with mock.patch.object(storage, "resolve_data_dir", return_value=self.data_dir) as resolver:
            result = self.run_cli("list", "-a", "007", data_dir=None)
        self.assertEqual(result.code, 0)
        resolver.assert_called_once_with()

    def test_disk_full_keeps_data(self) -> None:
        self.create()
        before = self.snapshot()
        with mock.patch("mi6.core.storage.os.replace", side_effect=OSError(errno.ENOSPC, "No space left")):
            result = self.create(name="GOLDENEYE", passwords=[PASSWORD])
        self.assert_failure(
            result,
            messages.ERR_DATA_ACCESS.format(path=self.missions_file, reason=messages.ERRNO_REASONS["ENOSPC"]),
        )
        self.assertEqual(self.snapshot(), before)

    def test_unknown_errno_name(self) -> None:
        error = DataAccessError(self.missions_file, "EWEIRD")
        with mock.patch.object(operations, "list_active_missions", side_effect=error):
            result = self.run_cli("list", "-a", "007")
        self.assert_failure(
            result,
            messages.ERR_DATA_ACCESS.format(path=self.missions_file,
                                            reason=messages.ERRNO_UNKNOWN.format(name="EWEIRD")),
        )

    def test_unexpected_error_hides_traceback(self) -> None:
        with mock.patch.object(operations, "list_active_missions", side_effect=RuntimeError("secret detail")):
            result = self.run_cli("list", "-a", "007")
        self.assert_failure(result, messages.UNEXPECTED)
        self.assertNotIn("secret detail", result.err)

    def test_paths_in_errors_are_sanitized(self) -> None:
        error = DataAccessError("/tmp/\x1b[31mevil‮", "EACCES")
        with mock.patch.object(operations, "list_active_missions", side_effect=error):
            result = self.run_cli("list", "-a", "007")
        self.assertEqual(result.code, 3)
        self.assertNotIn("\x1b", result.err)
        self.assertNotIn("‮", result.err)
        self.assertIn("/tmp/?[31mevil?", result.err)


# --- Exit code 130 -----------------------------------------------------------


class InterruptTest(CliTestCase):
    def assert_aborted(self, result: SimpleNamespace) -> None:
        self.assertEqual(result.code, 130)
        self.assertEqual(result.err.splitlines()[-1], messages.ABORTED_BY_AGENT)

    def test_ctrl_c_at_password_on_create(self) -> None:
        self.create()
        before = self.snapshot()
        self.assert_aborted(self.create(name="GOLDENEYE", passwords=KeyboardInterrupt()))
        self.assertEqual(self.snapshot(), before)

    def test_ctrl_c_at_first_password_creates_nothing(self) -> None:
        self.assert_aborted(self.create(passwords=[PASSWORD, KeyboardInterrupt()]))
        self.assertFalse(self.data_dir.exists())

    def test_ctrl_c_while_reading_report(self) -> None:
        result = self.run_cli("create", "-a", "007", "-n", "SKYFALL", "-t", "4", stdin=InterruptedStdin())
        self.assert_aborted(result)
        self.assertFalse(self.data_dir.exists())

    def test_ctrl_c_at_password_on_archive(self) -> None:
        self.create()
        before = self.snapshot()
        self.assert_aborted(self.run_cli("archive", "-a", "007", "-n", "SKYFALL", passwords=KeyboardInterrupt()))
        self.assertEqual(self.snapshot(), before)

    def test_ctrl_c_during_write(self) -> None:
        self.create()
        before = self.snapshot()
        with mock.patch("mi6.core.storage.os.replace", side_effect=KeyboardInterrupt):
            self.assert_aborted(self.create(name="GOLDENEYE", passwords=[PASSWORD]))
        self.assertEqual(self.snapshot(), before)

    def test_ctrl_d_at_password_prompt(self) -> None:
        self.assert_aborted(self.create(passwords=EOFError()))
        self.assertFalse(self.data_dir.exists())


# --- Output encoding (RF-7.6) ------------------------------------------------


class OutputEncodingTest(CliTestCase):
    def test_ascii_stdout_does_not_fail(self) -> None:
        self.create()
        raw = io.BytesIO()
        stdout = io.TextIOWrapper(raw, encoding="ascii")
        with mock.patch("mi6.cli.prompts.require_terminal"), redirect_stdout(stdout), \
                redirect_stderr(io.StringIO()):
            code = main(["list", "-a", "007"], data_dir=self.data_dir)
        stdout.flush()
        self.assertEqual(code, 0)
        self.assertIn(b"MISIONES ACTIVAS ? AGENTE 007", raw.getvalue())
        self.assertIn(b"RIESGO GLOBAL: 4 ? BAJO", raw.getvalue())

    def test_ascii_stderr_does_not_fail(self) -> None:
        raw = io.BytesIO()
        stderr = io.TextIOWrapper(raw, encoding="ascii")
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = main(["list", "-a", "000"], data_dir=self.data_dir)
        stderr.flush()
        self.assertEqual(code, 1)
        self.assertIn(b"Acceso denegado", raw.getvalue())

    def test_print_safe_without_reconfigure(self) -> None:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="ascii", errors="strict")
        render.print_safe("CRÍTICO · Ñandú 🦩", file=stream)
        self.assertEqual(raw.getvalue(), b"CR?TICO ? ?and? ?\n")

    def test_print_safe_defaults_to_stdout(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            render.print_safe("Ñandú")
        self.assertEqual(stdout.getvalue(), "Ñandú\n")


# --- render ------------------------------------------------------------------


def use_timezone(test: MI6TestCase, name: str) -> None:
    patcher = mock.patch.dict(os.environ, {"TZ": name})
    patcher.start()
    time.tzset()
    test.addCleanup(time.tzset)
    test.addCleanup(patcher.stop)


def make_mission(name: str, threat: int, created_at: datetime) -> Mission:
    return Mission(name, threat, MissionStatus.ACTIVE, created_at, "gAAAAAB-token")


class RenderTest(MI6TestCase):
    def test_plan_example_is_reproduced_exactly(self) -> None:
        use_timezone(self, "Europe/London")
        report = RiskReport(
            active_missions=(
                make_mission("SKYFALL", 4, datetime(2026, 10, 20, 9, 15, 42, tzinfo=timezone(timedelta(hours=1)))),
                make_mission("GOLDENEYE", 3, datetime(2026, 10, 26, 14, 32, 7, tzinfo=timezone.utc)),
            ),
            total=7,
            level=RiskLevel.MEDIUM,
        )
        expected = (
            "MISIONES ACTIVAS · AGENTE 007\n"
            "NOMBRE CLAVE                    AMENAZA  REGISTRO\n"
            "SKYFALL                         4        2026-10-20 09:15\n"
            "GOLDENEYE                       3        2026-10-26 14:32\n"
            "\n"
            "RIESGO GLOBAL: 7 · MEDIO"
        )
        self.assertEqual(render.format_mission_list("007", report), expected)

    def test_empty_report(self) -> None:
        report = RiskReport(active_missions=(), total=0, level=RiskLevel.LOW)
        self.assertEqual(
            render.format_mission_list("006", report),
            "Sin misiones activas, agente 006. Disfrute del martini.\nRIESGO GLOBAL: 0 · BAJO",
        )

    def test_longest_code_name_keeps_columns(self) -> None:
        name = "A" * 30
        report = RiskReport((make_mission(name, 5, self.now),), 5, RiskLevel.LOW)
        row = render.format_mission_list("007", report).splitlines()[2]
        self.assertEqual(row.index("5"), 32)

    def test_local_time_conversion(self) -> None:
        use_timezone(self, "America/New_York")
        moment = datetime(2026, 10, 26, 14, 32, 7, tzinfo=timezone.utc)
        self.assertEqual(render.format_local_datetime(moment), "2026-10-26 10:32")
        use_timezone(self, "UTC")
        self.assertEqual(render.format_local_datetime(moment), "2026-10-26 14:32")

    def test_labels(self) -> None:
        self.assertEqual(render.status_label(MissionStatus.ACTIVE), "ACTIVA")
        self.assertEqual(render.status_label("archived"), "ARCHIVADA")
        self.assertEqual(
            [render.risk_label(level) for level in RiskLevel], ["BAJO", "MEDIO", "CRÍTICO"],
        )
        self.assertEqual(render.risk_line(RiskReport((), 11, RiskLevel.CRITICAL)), "RIESGO GLOBAL: 11 · CRÍTICO")

    def test_sanitize_neutralizes_control_sequences(self) -> None:
        cases = {
            "\x1b[2J": "?[2J",
            "\x1b]0;pwned\x07": "?]0;pwned?",
            "abc‮def": "abc?def",
            "a​b": "a?b",
            "line\nbreak\r": "line?break?",
            "tab\t": "tab?",
            "\x00\x7f\x9b": "???",
            "a b ": "a?b?",
            "\ud800": "?",
            "": "?",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=repr(raw)):
                self.assertEqual(render.sanitize_output(raw), expected)

    def test_sanitize_keeps_printable_text(self) -> None:
        for text in ("SKYFALL", "Ñandú pingüino", "🦩", "2026-10-26 14:32", "/home/agente/.mi6"):
            with self.subTest(text=text):
                self.assertEqual(render.sanitize_output(text), text)
        self.assertEqual(render.sanitize_output(4), "4")

    def test_stored_data_is_sanitized_in_the_table(self) -> None:
        report = RiskReport((make_mission("EVIL\x1b[2J", 1, self.now),), 1, RiskLevel.LOW)
        output = render.format_mission_list("007\x1b[0m", report)
        self.assertNotIn("\x1b", output)
        self.assertIn("EVIL?[2J", output)
        self.assertIn("AGENTE 007?[0m", output)


# --- prompts -----------------------------------------------------------------


class RequireTerminalTest(MI6TestCase):
    def test_no_tty(self) -> None:
        with mock.patch("mi6.cli.prompts.os.open", side_effect=OSError(errno.ENXIO, "no tty")):
            with self.assertRaises(NoTerminalError):
                prompts.require_terminal()

    def test_tty_is_opened_and_closed(self) -> None:
        with mock.patch("mi6.cli.prompts.os.open", return_value=99) as opener, \
                mock.patch("mi6.cli.prompts.os.close") as closer:
            prompts.require_terminal()
        path, flags = opener.call_args.args
        self.assertEqual(path, "/dev/tty")
        self.assertEqual(flags, os.O_RDWR | os.O_NOCTTY)
        closer.assert_called_once_with(99)


class PromptPasswordTest(MI6TestCase):
    def test_reads_through_getpass_after_checking_terminal(self) -> None:
        order = []
        with mock.patch("mi6.cli.prompts.require_terminal", side_effect=lambda: order.append("tty")), \
                mock.patch("mi6.cli.prompts.getpass.getpass",
                           side_effect=lambda prompt: order.append(prompt) or PASSWORD):
            self.assertEqual(prompts.prompt_password("Contraseña: "), PASSWORD)
        self.assertEqual(order, ["tty", "Contraseña: "])

    def test_no_terminal_never_calls_getpass(self) -> None:
        with mock.patch("mi6.cli.prompts.require_terminal", side_effect=NoTerminalError()), \
                mock.patch("mi6.cli.prompts.getpass.getpass") as reader:
            with self.assertRaises(NoTerminalError):
                prompts.prompt_password("x")
        reader.assert_not_called()

    def test_echoing_fallback_is_refused(self) -> None:
        def insecure_getpass(prompt: str) -> str:
            warnings.warn("Can not control echo on the terminal.", getpass.GetPassWarning)
            return "leaked"

        with mock.patch("mi6.cli.prompts.require_terminal"), \
                mock.patch("mi6.cli.prompts.getpass.getpass", side_effect=insecure_getpass):
            with self.assertRaises(NoTerminalError):
                prompts.prompt_password("x")

    def test_new_password_is_read_twice(self) -> None:
        with mock.patch("mi6.cli.prompts.require_terminal"), \
                mock.patch("mi6.cli.prompts.getpass.getpass", side_effect=["uno-uno-1", "dos-dos-2"]) as reader:
            self.assertEqual(prompts.read_new_password("A: ", "B: "), ("uno-uno-1", "dos-dos-2"))
        self.assertEqual([c.args[0] for c in reader.call_args_list], ["A: ", "B: "])


class ReadReportBodyTest(MI6TestCase):
    def read(self, stdin: object) -> tuple[str, str]:
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), redirect_stderr(stderr):
            body = prompts.read_report_body()
        return body, stderr.getvalue()

    def test_piped_text_without_prompt(self) -> None:
        self.assertEqual(self.read(io.StringIO("Objetivo neutralizado.\n")), ("Objetivo neutralizado.\n", ""))

    def test_piped_bytes_are_decoded_as_utf8(self) -> None:
        stdin = io.TextIOWrapper(io.BytesIO("Ñandú 🦩\r\n".encode("utf-8")), encoding="latin-1")
        self.assertEqual(self.read(stdin), ("Ñandú 🦩\r\n", ""))

    def test_interactive_input_until_eof(self) -> None:
        body, err = self.read(InteractiveStdin("Línea 1\nLínea 2\n"))
        self.assertEqual(body, "Línea 1\nLínea 2\n")
        self.assertEqual(err, messages.REPORT_PROMPT + "\n")

    def test_invalid_utf8_bytes(self) -> None:
        stdin = io.TextIOWrapper(io.BytesIO(b"\xff\xfe"), encoding="utf-8")
        with self.assertRaises(ValidationError) as ctx:
            self.read(stdin)
        self.assertEqual((ctx.exception.field, ctx.exception.rule), ("report", "encoding"))

    def test_surrogate_escaped_text(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.read(io.StringIO("informe \udcff"))
        self.assertEqual(ctx.exception.rule, "encoding")

    def test_closed_stdin_gives_empty_report(self) -> None:
        self.assertEqual(self.read(None), ("", ""))


# --- messages and boundaries -------------------------------------------------


class MessagesTest(MI6TestCase):
    PLACEHOLDERS = {
        "CREATE_OK": {"code_name", "threat", "agent"},
        "LIST_HEADER": {"agent"},
        "LIST_RISK": {"total", "level"},
        "LIST_EMPTY": {"agent"},
        "ARCHIVE_PREVIEW": {"code_name", "threat"},
        "ARCHIVE_OK": {"code_name"},
        "PASSWORD_NEW": {"agent"},
        "ERR_REPORT_LENGTH": {"length"},
        "ERR_VALIDATION": {"field"},
        "ERR_DUPLICATE": {"code_name", "status_es"},
        "ERR_NOT_FOUND": {"code_name"},
        "ERR_DATA_ACCESS": {"path", "reason"},
        "ERR_PERMISSIONS": {"path", "current", "expected"},
        "ERR_OWNER": {"path"},
        "ERR_SYMLINK": {"path"},
        "ERR_CORRUPT": {"path"},
        "ERRNO_UNKNOWN": {"name"},
    }
    PLAN_CONSTANTS = [
        "CREATE_OK", "LIST_HEADER", "LIST_RISK", "LIST_EMPTY", "ARCHIVE_PREVIEW", "ARCHIVE_OK",
        "REPORT_PROMPT", "PASSWORD_PROMPT", "PASSWORD_NEW", "PASSWORD_REPEAT", "ERR_AGENT_CODE",
        "ERR_THREAT", "ERR_CODE_NAME", "ERR_REPORT_EMPTY", "ERR_REPORT_LENGTH", "ERR_REPORT_CHARS",
        "ERR_REPORT_ENCODING", "ERR_PASSWORD_SHORT", "ERR_PASSWORD_MISMATCH", "ERR_AUTH", "ERR_DUPLICATE",
        "ERR_NOT_FOUND", "ERR_USAGE", "ERR_NO_TERMINAL", "ERR_DATA_ACCESS", "ERR_PERMISSIONS",
        "ERR_SYMLINK", "ERR_CORRUPT", "ERR_IN_PROGRESS", "ERR_ROOT", "ERR_NO_HOME", "UNEXPECTED",
        "ABORTED_BY_AGENT", "HELP",
    ]

    def test_every_plan_constant_exists(self) -> None:
        for name in self.PLAN_CONSTANTS:
            with self.subTest(name=name):
                self.assertIsInstance(getattr(messages, name), str)
                self.assertTrue(getattr(messages, name).strip())

    def test_placeholders_match(self) -> None:
        formatter = string.Formatter()
        for name in dir(messages):
            value = getattr(messages, name)
            if not name.isupper() or not isinstance(value, str):
                continue
            with self.subTest(name=name):
                fields = {field for _, field, _, _ in formatter.parse(value) if field}
                self.assertEqual(fields, self.PLACEHOLDERS.get(name, set()))

    def test_every_core_validation_rule_has_a_message(self) -> None:
        raised = [
            InvalidAgentCodeError(),
            PasswordPolicyError("too_short"),
            PasswordPolicyError("mismatch"),
            *[ValidationError("threat_level", rule) for rule in ("range", "type")],
            *[ValidationError("code_name", rule) for rule in ("empty", "length", "chars", "type")],
            *[ValidationError("report", rule) for rule in ("empty", "length", "chars", "encoding")],
        ]
        for error in raised:
            with self.subTest(field=error.field, rule=error.rule):
                self.assertIn((error.field, error.rule), messages.VALIDATION_MESSAGES)

    def test_lookup_tables_cover_core_values(self) -> None:
        self.assertEqual(set(messages.STATUS_LABELS), {s.value for s in MissionStatus})
        self.assertEqual(set(messages.DUPLICATE_STATUS_LABELS), {s.value for s in MissionStatus})
        self.assertEqual(set(messages.RISK_LABELS), {level.value for level in RiskLevel})
        self.assertEqual(set(messages.UNSAFE_ENVIRONMENT_MESSAGES), {"root", "no_home"})
        self.assertEqual(set(messages.FIELD_LABELS), {"agent_code", "threat_level", "code_name", "report", "password"})

    def test_errno_names_are_real(self) -> None:
        known = set(errno.errorcode.values())
        for name in messages.ERRNO_REASONS:
            with self.subTest(name=name):
                self.assertIn(name, known)

    def test_module_imports_nothing(self) -> None:
        source = (PROJECT_ROOT / "mi6" / "cli" / "messages.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^\s*(import|from)\s")


class ErrorMappingTest(MI6TestCase):
    def test_exit_codes(self) -> None:
        cases = [
            (ValidationError("report", "empty"), 1),
            (InvalidAgentCodeError(), 1),
            (PasswordPolicyError("mismatch"), 1),
            (AuthenticationError(), 1),
            (DuplicateMissionError("X", "active"), 1),
            (MissionNotFoundError("X"), 1),
            (NoTerminalError(), 2),
            (DataAccessError("/x", "EIO"), 3),
            (InsecurePermissionsError("/x", 0o644, 0o600), 3),
            (SymlinkError("/x"), 3),
            (CorruptDataError("invalid"), 3),
            (OperationInProgressError(), 3),
            (UnsafeEnvironmentError("root"), 3),
            (RuntimeError("boom"), 3),
            (OSError("raw"), 3),
        ]
        for error, code in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(cli_main._exit_code(error), code)

    def test_unknown_validation_rule_uses_field_label(self) -> None:
        message = cli_main._error_message(ValidationError("report", "novel_rule"))
        self.assertEqual(message, messages.ERR_VALIDATION.format(field="el informe"))

    def test_corrupt_without_path(self) -> None:
        self.assertEqual(
            cli_main._error_message(CorruptDataError("invalid")),
            messages.ERR_CORRUPT.format(path=messages.UNKNOWN_PATH),
        )

    def test_unknown_environment_reason(self) -> None:
        self.assertEqual(cli_main._error_message(UnsafeEnvironmentError("other")), messages.UNEXPECTED)


class ParserTest(MI6TestCase):
    def test_parsed_values_are_raw_strings(self) -> None:
        args = build_parser().parse_args(["create", "-a", " 007 ", "--name", "skyfall", "-t", "4"])
        self.assertEqual((args.command, args.agent, args.code_name, args.threat), ("create", " 007 ", "skyfall", "4"))

    def test_main_signature(self) -> None:
        parameters = inspect.signature(main).parameters
        self.assertEqual(list(parameters), ["argv", "data_dir"])
        self.assertIsNone(parameters["argv"].default)
        self.assertIsNone(parameters["data_dir"].default)


class LayerBoundaryTest(MI6TestCase):
    """Constitution, principle 3: the core never depends on the terminal or on the CLI."""

    def test_core_has_no_terminal_access_or_cli_imports(self) -> None:
        pattern = r"(?m)^\s*(import (argparse|sys)\b|from (argparse|sys)\b|from mi6\.cli|import mi6\.cli)|\b(print|input)\("
        for path in sorted((PROJECT_ROOT / "mi6" / "core").glob("*.py")):
            with self.subTest(module=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), pattern)

    def test_spanish_text_only_in_messages(self) -> None:
        spanish = r"[áéíóúñÁÉÍÓÚÑ¿¡]"
        for path in sorted((PROJECT_ROOT / "mi6").rglob("*.py")):
            if path.name == "messages.py":
                continue
            with self.subTest(module=str(path.relative_to(PROJECT_ROOT))):
                self.assertNotRegex(path.read_text(encoding="utf-8"), spanish)
