"""End-to-end runs of ``python -m mi6`` on a real pseudo-terminal (RF-2.1, RF-2.7, RF-3.2, RF-7.3).

Unlike tests/test_cli.py, nothing is mocked here: getpass really talks to
/dev/tty, the terminal really disables echo, and Ctrl+C really sends SIGINT.
The production KDF (600,000 iterations) is used.
"""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from mi6.cli import messages
from tests.test_base import IS_ROOT, MI6TestCase

try:
    import pty
except ImportError:  # pragma: no cover - pty exists on every supported platform
    pty = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "clave-de-campo-77"
TIMEOUT_SECONDS = 30
CTRL_C = b"\x03"
CTRL_D = b"\x04"


@unittest.skipIf(pty is None, "pseudo-terminals are not available")
@unittest.skipIf(IS_ROOT, "mi6 refuses to run as root")
class RealTerminalTest(MI6TestCase):
    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "HOME": str(self.home),
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "LC_ALL": "C.UTF-8",
        }

    def run_in_pty(self, argv: list[str], script: list[tuple[str, bytes]]) -> tuple[int, str]:
        """Run mi6 with a pty as controlling terminal; send each input once its prompt appears."""
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(self.tmp_path)
                os.execve(sys.executable, [sys.executable, "-m", "mi6", *argv], self.env())
            finally:
                os._exit(127)
        output = b""
        cursor = 0
        pending = [(prompt.encode("utf-8"), data) for prompt, data in script]
        deadline = time.monotonic() + TIMEOUT_SECONDS
        try:
            while True:
                if pending:
                    found = output.find(pending[0][0], cursor)
                    if found != -1:
                        cursor = found + len(pending[0][0])
                        os.write(fd, pending.pop(0)[1])
                        continue
                if time.monotonic() > deadline:
                    os.kill(pid, signal.SIGKILL)
                    self.fail(f"mi6 did not finish; output so far: {output!r}")
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    continue
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
        finally:
            os.close(fd)
            _, status = os.waitpid(pid, 0)
        self.assertEqual(pending, [], f"prompts never shown; output: {output!r}")
        return os.waitstatus_to_exitcode(status), output.decode("utf-8", errors="replace")

    def create_first_mission(self) -> tuple[int, str]:
        return self.run_in_pty(
            ["create", "-a", "007", "-n", "SKYFALL", "-t", "4"],
            [
                (messages.REPORT_PROMPT, "Ñandú avistado en Estambul.\n".encode("utf-8")),
                ("Estambul.", CTRL_D),
                (messages.PASSWORD_NEW.format(agent="007"), PASSWORD.encode() + b"\n"),
                (messages.PASSWORD_REPEAT, PASSWORD.encode() + b"\n"),
            ],
        )

    def test_full_flow_with_hidden_password(self) -> None:
        code, output = self.create_first_mission()
        self.assertEqual(code, 0, output)
        self.assertIn(messages.CREATE_OK.format(code_name="SKYFALL", threat=4, agent="007"), output)
        # Control: the terminal echoes ordinary input, so the report is visible
        # and the missing password proves getpass really disabled the echo.
        self.assertIn("Ñandú avistado en Estambul.", output)
        self.assertNotIn(PASSWORD, output)
        self.assertEqual(self.mode_of(self.missions_file), 0o600)
        self.assertNotIn("Estambul".encode(), self.missions_file.read_bytes())

        code, output = self.run_in_pty(["list", "-a", "007"], [])
        self.assertEqual(code, 0, output)
        self.assertIn("SKYFALL", output)
        self.assertIn(messages.LIST_RISK.format(total=4, level="BAJO"), output)
        self.assertNotIn("Estambul", output)

        code, output = self.run_in_pty(
            ["archive", "-a", "007", "-n", "SKYFALL"],
            [(messages.PASSWORD_PROMPT, PASSWORD.encode() + b"\n")],
        )
        self.assertEqual(code, 0, output)
        self.assertLess(
            output.index(messages.ARCHIVE_PREVIEW.format(code_name="SKYFALL", threat=4)),
            output.index(messages.PASSWORD_PROMPT),
        )
        self.assertIn(messages.ARCHIVE_OK.format(code_name="SKYFALL"), output)
        self.assertNotIn(PASSWORD, output)

    def test_wrong_password_on_real_terminal(self) -> None:
        self.assertEqual(self.create_first_mission()[0], 0)
        before = self.snapshot_dir()
        code, output = self.run_in_pty(
            ["archive", "-a", "007", "-n", "SKYFALL"],
            [(messages.PASSWORD_PROMPT, b"clave-equivocada\n")],
        )
        self.assertEqual(code, 1, output)
        self.assertIn(messages.ERR_AUTH, output)
        self.assertNotIn("clave-equivocada", output)
        self.assertEqual(self.snapshot_dir(), before)

    def test_ctrl_c_at_password_prompt(self) -> None:
        self.assertEqual(self.create_first_mission()[0], 0)
        before = self.snapshot_dir()
        code, output = self.run_in_pty(
            ["archive", "-a", "007", "-n", "SKYFALL"],
            [(messages.PASSWORD_PROMPT, CTRL_C)],
        )
        self.assertEqual(code, 130, output)
        self.assertIn(messages.ABORTED_BY_AGENT, output)
        self.assertEqual(self.snapshot_dir(), before)

    def test_ctrl_c_while_typing_the_report(self) -> None:
        code, output = self.run_in_pty(
            ["create", "-a", "007", "-n", "SKYFALL", "-t", "4"],
            [(messages.REPORT_PROMPT, b"medio informe"), ("medio informe", CTRL_C)],
        )
        self.assertEqual(code, 130, output)
        self.assertFalse(self.data_dir.exists())

    def test_no_controlling_terminal_exits_2(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "mi6", "create", "-a", "007", "-n", "SKYFALL", "-t", "4"],
            input="Informe por tubería.\n",
            capture_output=True,
            text=True,
            env=self.env(),
            cwd=self.tmp_path,
            start_new_session=True,
            timeout=TIMEOUT_SECONDS,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(completed.stderr, messages.ERR_NO_TERMINAL + "\n")
        self.assertFalse(self.data_dir.exists())
