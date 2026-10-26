"""Structural validation of a loaded missions.json (RF-6.4, RF-6.5; plan, section 2.3).

Any unknown or missing key, wrong type or rule violation at any level makes
the whole document corrupt: CorruptDataError("invalid").
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from datetime import datetime
from typing import Any

from mi6.core.errors import CorruptDataError
from mi6.core.models import (
    KDF_ALGORITHM,
    SCHEMA_VERSION,
    AgentRecord,
    KdfParams,
    Mission,
    MissionsDocument,
    MissionStatus,
)

SALT_SIZE = 16
MIN_THREAT_LEVEL = 1
MAX_THREAT_LEVEL = 5

_DOCUMENT_KEYS = frozenset({"schema_version", "agents"})
_AGENT_KEYS = frozenset({"kdf", "key_check", "missions"})
_KDF_KEYS = frozenset({"algorithm", "iterations", "salt"})
_MISSION_KEYS = frozenset({"code_name", "threat_level", "status", "created_at", "report_token"})

_AGENT_CODE_RE = re.compile(r"00[1-9]")
_CODE_NAME_RE = re.compile(r"[A-Z0-9-]{1,30}")
_STANDARD_B64_RE = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_URLSAFE_B64_RE = re.compile(r"[A-Za-z0-9_-]+={0,2}")

# Fernet token layout: version (1) + timestamp (8) + IV (16) + ciphertext (16 * n) + HMAC (32).
_FERNET_VERSION = 0x80
_FERNET_OVERHEAD = 57
_FERNET_BLOCK = 16
_FERNET_MIN_SIZE = _FERNET_OVERHEAD + _FERNET_BLOCK


class _InvalidDocument(Exception):
    """Internal signal carrying where validation failed."""


def parse_document(raw: Any, *, path: str | os.PathLike[str] | None = None) -> MissionsDocument:
    """Validate the raw JSON value and return it as a MissionsDocument."""
    try:
        return _parse_document(raw)
    except _InvalidDocument as exc:
        raise CorruptDataError("invalid", path=path) from exc


def is_fernet_token(value: Any) -> bool:
    """True if ``value`` has the shape of a Fernet token, without decrypting it."""
    if not isinstance(value, str) or _URLSAFE_B64_RE.fullmatch(value) is None:
        return False
    try:
        data = base64.urlsafe_b64decode(value)
    except (binascii.Error, ValueError):
        return False
    return (
        len(data) >= _FERNET_MIN_SIZE
        and (len(data) - _FERNET_OVERHEAD) % _FERNET_BLOCK == 0
        and data[0] == _FERNET_VERSION
    )


def _parse_document(raw: Any) -> MissionsDocument:
    document = _require_object(raw, _DOCUMENT_KEYS, "document")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise _InvalidDocument("unknown schema_version")
    agents = document["agents"]
    if not isinstance(agents, dict):
        raise _InvalidDocument("agents is not an object")
    records = {}
    for code, agent in agents.items():
        if _AGENT_CODE_RE.fullmatch(code) is None:
            raise _InvalidDocument(f"invalid agent code {code!r}")
        records[code] = _parse_agent(agent, code)
    return MissionsDocument(schema_version=version, agents=records)


def _parse_agent(raw: Any, code: str) -> AgentRecord:
    agent = _require_object(raw, _AGENT_KEYS, f"agents.{code}")
    kdf = _parse_kdf(agent["kdf"], code)
    if not is_fernet_token(agent["key_check"]):
        raise _InvalidDocument(f"agents.{code}.key_check is not a Fernet token")
    raw_missions = agent["missions"]
    if not isinstance(raw_missions, list):
        raise _InvalidDocument(f"agents.{code}.missions is not an array")
    missions = []
    seen: set[str] = set()
    for index, raw_mission in enumerate(raw_missions):
        mission = _parse_mission(raw_mission, f"agents.{code}.missions[{index}]")
        if mission.code_name in seen:
            raise _InvalidDocument(f"agents.{code}: duplicate code_name {mission.code_name}")
        seen.add(mission.code_name)
        missions.append(mission)
    return AgentRecord(kdf=kdf, key_check=agent["key_check"], missions=missions)


def _parse_kdf(raw: Any, code: str) -> KdfParams:
    where = f"agents.{code}.kdf"
    kdf = _require_object(raw, _KDF_KEYS, where)
    if kdf["algorithm"] != KDF_ALGORITHM:
        raise _InvalidDocument(f"{where}.algorithm is not supported")
    iterations = kdf["iterations"]
    if type(iterations) is not int or iterations < 1:
        raise _InvalidDocument(f"{where}.iterations must be a positive integer")
    salt = kdf["salt"]
    if not _is_salt(salt):
        raise _InvalidDocument(f"{where}.salt must be Base64 of {SALT_SIZE} bytes")
    return KdfParams(salt=salt, iterations=iterations, algorithm=KDF_ALGORITHM)


def _parse_mission(raw: Any, where: str) -> Mission:
    mission = _require_object(raw, _MISSION_KEYS, where)
    code_name = mission["code_name"]
    if not isinstance(code_name, str) or _CODE_NAME_RE.fullmatch(code_name) is None:
        raise _InvalidDocument(f"{where}.code_name is invalid")
    threat_level = mission["threat_level"]
    if type(threat_level) is not int or not MIN_THREAT_LEVEL <= threat_level <= MAX_THREAT_LEVEL:
        raise _InvalidDocument(f"{where}.threat_level must be an integer from 1 to 5")
    status = mission["status"]
    if type(status) is not str or status not in {member.value for member in MissionStatus}:
        raise _InvalidDocument(f"{where}.status is invalid")
    created_at = _parse_timestamp(mission["created_at"], where)
    if not is_fernet_token(mission["report_token"]):
        raise _InvalidDocument(f"{where}.report_token is not a Fernet token")
    return Mission(
        code_name=code_name,
        threat_level=threat_level,
        status=MissionStatus(status),
        created_at=created_at,
        report_token=mission["report_token"],
    )


def _parse_timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise _InvalidDocument(f"{where}.created_at is not a string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _InvalidDocument(f"{where}.created_at is not ISO 8601") from exc
    if parsed.utcoffset() is None:
        raise _InvalidDocument(f"{where}.created_at has no timezone")
    return parsed


def _is_salt(value: Any) -> bool:
    if not isinstance(value, str) or _STANDARD_B64_RE.fullmatch(value) is None:
        return False
    try:
        return len(base64.b64decode(value, validate=True)) == SALT_SIZE
    except (binascii.Error, ValueError):
        return False


def _require_object(value: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _InvalidDocument(f"{where} is not an object")
    if set(value) != keys:
        raise _InvalidDocument(f"{where} has unexpected or missing keys")
    return value
