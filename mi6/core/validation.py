"""Pure format rules for agent input (RF-1.1, RF-2.3, RF-3.5, RF-3.7 to RF-3.9).

Every validator either returns the cleaned value or raises a ValidationError
subclass describing the field and the broken rule. No I/O happens here.
"""

from __future__ import annotations

import re
import unicodedata

from mi6.core.errors import InvalidAgentCodeError, PasswordPolicyError, ValidationError

CODE_NAME_MAX_LENGTH = 30
REPORT_MAX_LENGTH = 500
PASSWORD_MIN_LENGTH = 8

# Literal ASCII classes on purpose: \d would also match fullwidth or Arabic digits.
_AGENT_CODE_RE = re.compile(r"00[1-9]")
_THREAT_LEVEL_RE = re.compile(r"[1-5]")
_CODE_NAME_RE = re.compile(r"[A-Za-z0-9-]+")

_ZERO_WIDTH_JOINER = "\u200d"
_ALLOWED_CONTROL_CHARS = frozenset("\n\t")
_FORBIDDEN_CATEGORIES = frozenset({"Cs", "Co", "Cn"})


def validate_agent_code(raw: str) -> str:
    """Return the agent code without surrounding whitespace if it is 001 to 009."""
    if not isinstance(raw, str):
        raise InvalidAgentCodeError()
    code = raw.strip()
    if _AGENT_CODE_RE.fullmatch(code) is None:
        raise InvalidAgentCodeError()
    return code


def validate_threat_level(raw: str) -> int:
    """Return the threat level as an int if it is a single ASCII digit from 1 to 5."""
    if not isinstance(raw, str):
        raise ValidationError("threat_level", "type")
    level = raw.strip()
    if _THREAT_LEVEL_RE.fullmatch(level) is None:
        raise ValidationError("threat_level", "range")
    return int(level)


def validate_code_name(raw: str) -> str:
    """Return the code name in upper case if it has 1 to 30 chars from A-Z, a-z, 0-9 and '-'."""
    if not isinstance(raw, str):
        raise ValidationError("code_name", "type")
    if not raw:
        raise ValidationError("code_name", "empty")
    if len(raw) > CODE_NAME_MAX_LENGTH:
        raise ValidationError("code_name", "length", length=len(raw))
    if _CODE_NAME_RE.fullmatch(raw) is None:
        raise ValidationError("code_name", "chars")
    return raw.upper()


def normalize_report(raw: str) -> str:
    """Return the normalized report or raise ValidationError(field="report").

    Steps (plan, section 4.2): CRLF to LF, strip (Unicode whitespace too),
    NFC, length 1 to 500 code points, then reject Cc except LF and TAB,
    Cf except ZWJ, and every Cs, Co and Cn character.
    """
    if not isinstance(raw, str):
        raise ValidationError("report", "encoding")
    report = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").strip())
    if not report:
        raise ValidationError("report", "empty")
    if len(report) > REPORT_MAX_LENGTH:
        raise ValidationError("report", "length", length=len(report))
    if not all(_is_allowed_report_char(char) for char in report):
        raise ValidationError("report", "chars")
    return report


def validate_new_password(password: str, confirmation: str) -> str:
    """Return the NFC password if it has at least 8 chars and matches its confirmation."""
    if not isinstance(password, str) or not isinstance(confirmation, str):
        raise PasswordPolicyError("mismatch")
    normalized = unicodedata.normalize("NFC", password)
    if len(normalized) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError("too_short")
    if normalized != unicodedata.normalize("NFC", confirmation):
        raise PasswordPolicyError("mismatch")
    return normalized


def _is_allowed_report_char(char: str) -> bool:
    category = unicodedata.category(char)
    if category == "Cc":
        return char in _ALLOWED_CONTROL_CHARS
    if category == "Cf":
        return char == _ZERO_WIDTH_JOINER
    return category not in _FORBIDDEN_CATEGORIES
