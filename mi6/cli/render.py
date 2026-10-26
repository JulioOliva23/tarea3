"""Screen formatting and output sanitizing (RF-4.2, RF-4.8, RF-7.6; plan, section 4.5)."""

from __future__ import annotations

import sys
import unicodedata
from datetime import datetime
from typing import TextIO

from mi6.cli import messages
from mi6.core.models import RiskReport

CODE_NAME_WIDTH = 32
THREAT_WIDTH = 9
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
REPLACEMENT = "?"

# Control and format characters (ANSI escapes, bidi overrides, zero-width
# characters), plus surrogates, private use, unassigned code points and
# line/paragraph separators, none of which may reach the terminal raw.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def sanitize_output(value: object) -> str:
    """Return ``str(value)`` with every unsafe character replaced by '?'."""
    return "".join(
        REPLACEMENT if unicodedata.category(char) in _UNSAFE_CATEGORIES else char
        for char in str(value)
    )


def format_local_datetime(moment: datetime) -> str:
    """Return the moment in the local timezone as ``YYYY-MM-DD HH:MM``."""
    return moment.astimezone().strftime(DATETIME_FORMAT)


def status_label(status: str) -> str:
    return messages.STATUS_LABELS[str(status)]


def risk_label(level: str) -> str:
    return messages.RISK_LABELS[str(level)]


def risk_line(report: RiskReport) -> str:
    return messages.LIST_RISK.format(total=report.total, level=risk_label(report.level))


def format_mission_list(agent_code: str, report: RiskReport) -> str:
    """Return the ``list`` output: the active missions table and the global risk.

    Report texts are never part of a RiskReport, so they can never be shown.
    """
    agent = sanitize_output(agent_code)
    if not report.active_missions:
        return "\n".join([messages.LIST_EMPTY.format(agent=agent), risk_line(report)])
    lines = [
        messages.LIST_HEADER.format(agent=agent),
        _row(messages.LIST_COLUMN_CODE_NAME, messages.LIST_COLUMN_THREAT, messages.LIST_COLUMN_CREATED),
    ]
    for mission in report.active_missions:
        lines.append(
            _row(
                sanitize_output(mission.code_name),
                sanitize_output(mission.threat_level),
                format_local_datetime(mission.created_at),
            )
        )
    lines.extend(["", risk_line(report)])
    return "\n".join(lines)


def print_safe(text: str, *, file: TextIO | None = None) -> None:
    """Write one line, replacing characters the stream's encoding cannot represent."""
    stream = sys.stdout if file is None else file
    line = text + "\n"
    try:
        stream.write(line)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(line.encode(encoding, errors="replace").decode(encoding))
    stream.flush()


def _row(code_name: str, threat: str, created: str) -> str:
    return f"{code_name:<{CODE_NAME_WIDTH}}{threat:<{THREAT_WIDTH}}{created}"
