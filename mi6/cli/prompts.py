"""Interactive input: terminal check, hidden password and report body (RF-2.1, RF-2.7, RF-3.2).

The password is only ever read from /dev/tty through getpass, never echoed
and never taken from stdin, which may be carrying the report.
"""

from __future__ import annotations

import getpass
import os
import sys
import warnings

from mi6.cli import messages
from mi6.core.errors import ValidationError

TTY_PATH = "/dev/tty"


class NoTerminalError(Exception):
    """No interactive terminal is available to read the password (exit code 2)."""


def require_terminal() -> None:
    """Raise NoTerminalError unless /dev/tty can be opened for reading and writing."""
    try:
        fd = os.open(TTY_PATH, os.O_RDWR | os.O_NOCTTY)
    except OSError as exc:
        raise NoTerminalError() from exc
    os.close(fd)


def prompt_password(prompt: str) -> str:
    """Read a password from /dev/tty without echo.

    getpass falls back to an echoing read from stdin when /dev/tty is
    unusable and signals it with GetPassWarning; that fallback is refused.
    """
    require_terminal()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning as exc:
            raise NoTerminalError() from exc


def read_new_password(prompt: str, repeat_prompt: str) -> tuple[str, str]:
    """Read a new password twice. Comparing both entries is up to the core."""
    first = prompt_password(prompt)
    second = prompt_password(repeat_prompt)
    return first, second


def read_report_body() -> str:
    """Read the whole report from stdin: piped content, or typed text until EOF (Ctrl+D).

    Bytes are decoded as strict UTF-8, so invalid input raises
    ValidationError(field="report", rule="encoding") instead of being
    silently altered.
    """
    stream = sys.stdin
    if stream is None:
        return ""
    if stream.isatty():
        sys.stderr.write(messages.REPORT_PROMPT + "\n")
        sys.stderr.flush()
    buffer = getattr(stream, "buffer", None)
    try:
        if buffer is not None:
            return buffer.read().decode("utf-8")
        text = stream.read()
        text.encode("utf-8")
        return text
    except UnicodeError as exc:
        raise ValidationError("report", "encoding") from exc
