"""Use cases of mi6-cli: create, list and archive missions (RF-2 to RF-5; plan, section 4.4).

Every function receives ``data_dir`` explicitly. Lock-free pre-checks
(``preflight_create``, ``get_active_mission``) give the agent a fast answer;
the final operation validates everything again under the exclusive lock (D8).
"""

from __future__ import annotations

import dataclasses
import os
from datetime import datetime
from pathlib import Path

from mi6.core import crypto, schema, storage, validation
from mi6.core.errors import DuplicateMissionError, MissionNotFoundError, PasswordPolicyError
from mi6.core.models import (
    AgentRecord,
    KdfParams,
    Mission,
    MissionsDocument,
    MissionStatus,
    RiskReport,
)
from mi6.core.risk import compute_risk

DataDir = str | os.PathLike[str]


def agent_exists(data_dir: DataDir, agent_code: str) -> bool:
    """True if the agent code already has a password. Never creates anything."""
    code = validation.validate_agent_code(agent_code)
    return code in _read_snapshot(Path(data_dir)).agents


def preflight_create(
    data_dir: DataDir,
    agent_code: str,
    code_name: str,
    threat_level: str,
) -> tuple[str, str, int]:
    """Validate the clear-text fields and reject duplicates before asking for the report.

    Returns the cleaned ``(agent_code, code_name, threat_level)``. Writes nothing.
    """
    code, name, threat = _validate_mission_fields(agent_code, code_name, threat_level)
    record = _read_snapshot(Path(data_dir)).agents.get(code)
    if record is not None:
        _ensure_unique(record, name)
    return code, name, threat


def create_mission(
    data_dir: DataDir,
    agent_code: str,
    code_name: str,
    threat_level: str,
    report: str,
    password: str,
    password_confirmation: str | None = None,
    *,
    kdf_iterations: int = crypto.DEFAULT_ITERATIONS,
    now: datetime | None = None,
) -> Mission:
    """Register an ACTIVE mission with its report encrypted (RF-2.3 to RF-2.6, RF-3).

    A new agent code needs ``password_confirmation`` and gets a fresh salt and
    verifier; an existing one must present the password it set. On the very
    first use the data directory is created, and removed again if the first
    write does not complete, so a failure never leaves remnants behind.
    """
    data_dir = Path(data_dir)
    code, name, threat = _validate_mission_fields(agent_code, code_name, threat_level)
    clean_report = validation.normalize_report(report)
    created_at = _timestamp(now)
    _check_iterations(kdf_iterations)

    first_use = not storage.data_dir_exists(data_dir)
    if first_use:
        _new_agent_password(password, password_confirmation)
        storage.initialize_data_dir(data_dir)
    else:
        storage.check_no_symlinks(data_dir)

    with storage.exclusive_lock(data_dir):
        try:
            document = MissionsDocument() if first_use else _load_document(data_dir)
            record = document.agents.get(code)
            if record is None:
                new_password = _new_agent_password(password, password_confirmation)
                record, key = _new_agent(new_password, kdf_iterations)
            else:
                _ensure_unique(record, name)
                key = _unlock(record, password)
            mission = Mission(
                code_name=name,
                threat_level=threat,
                status=MissionStatus.ACTIVE,
                created_at=created_at,
                report_token=crypto.encrypt_report(key, clean_report),
            )
            updated = dataclasses.replace(record, missions=record.missions + (mission,))
            storage.write_document_atomic(data_dir, _with_agent(document, code, updated).to_dict())
        except BaseException:
            if first_use:
                storage.discard_uninitialized_data_dir(data_dir)
            raise
    return mission


def list_active_missions(data_dir: DataDir, agent_code: str) -> RiskReport:
    """Return the agent's active missions in registration order and their global risk.

    Needs no password and decrypts nothing (RF-4.1, RF-4.7). Without data it
    returns an empty LOW report and creates nothing (RF-4.5, RF-4.6).
    """
    code = validation.validate_agent_code(agent_code)
    record = _read_snapshot(Path(data_dir)).agents.get(code)
    return compute_risk(record.missions if record is not None else ())


def get_active_mission(data_dir: DataDir, agent_code: str, code_name: str) -> Mission:
    """Return an active mission without asking for the password (RF-5.1, RF-5.4)."""
    code = validation.validate_agent_code(agent_code)
    name = validation.validate_code_name(code_name)
    return _find_active(_read_snapshot(Path(data_dir)).agents.get(code), name)


def archive_mission(data_dir: DataDir, agent_code: str, code_name: str, password: str) -> Mission:
    """Mark an active mission ARCHIVED, keeping its encrypted report untouched (RF-5.2 to RF-5.5)."""
    data_dir = Path(data_dir)
    code = validation.validate_agent_code(agent_code)
    name = validation.validate_code_name(code_name)
    if not storage.data_dir_exists(data_dir):
        raise MissionNotFoundError(name)
    storage.check_no_symlinks(data_dir)

    with storage.exclusive_lock(data_dir):
        document = _load_document(data_dir)
        record = document.agents.get(code)
        mission = _find_active(record, name)
        _unlock(record, password)
        archived = dataclasses.replace(mission, status=MissionStatus.ARCHIVED)
        missions = tuple(archived if item is mission else item for item in record.missions)
        updated = dataclasses.replace(record, missions=missions)
        storage.write_document_atomic(data_dir, _with_agent(document, code, updated).to_dict())
    return archived


def _load_document(data_dir: Path) -> MissionsDocument:
    """Run every storage check and parse missions.json. The caller holds the lock."""
    storage.check_no_symlinks(data_dir)
    storage.check_permissions(data_dir)
    storage.check_no_remnants(data_dir)
    raw = storage.read_document(data_dir)
    return schema.parse_document(raw, path=storage.missions_path(data_dir))


def _read_snapshot(data_dir: Path) -> MissionsDocument:
    if not storage.data_dir_exists(data_dir):
        return MissionsDocument()
    storage.check_no_symlinks(data_dir)
    with storage.shared_lock(data_dir):
        return _load_document(data_dir)


def _validate_mission_fields(agent_code: str, code_name: str, threat_level: str) -> tuple[str, str, int]:
    return (
        validation.validate_agent_code(agent_code),
        validation.validate_code_name(code_name),
        validation.validate_threat_level(threat_level),
    )


def _ensure_unique(record: AgentRecord, code_name: str) -> None:
    existing = record.find_mission(code_name)
    if existing is not None:
        raise DuplicateMissionError(code_name, existing.status)


def _find_active(record: AgentRecord | None, code_name: str) -> Mission:
    mission = record.find_mission(code_name) if record is not None else None
    if mission is None or mission.status != MissionStatus.ACTIVE:
        raise MissionNotFoundError(code_name)
    return mission


def _new_agent_password(password: str, confirmation: str | None) -> str:
    if confirmation is None:
        raise PasswordPolicyError("mismatch")
    return validation.validate_new_password(password, confirmation)


def _new_agent(password: str, iterations: int) -> tuple[AgentRecord, bytes]:
    salt = crypto.new_salt()
    key = crypto.derive_key(password, salt, iterations)
    record = AgentRecord(
        kdf=KdfParams(salt=crypto.encode_salt(salt), iterations=iterations),
        key_check=crypto.make_key_check(key),
    )
    return record, key


def _unlock(record: AgentRecord, password: str) -> bytes:
    key = crypto.derive_key(password, crypto.decode_salt(record.kdf.salt), record.kdf.iterations)
    crypto.verify_key(key, record.key_check)
    return key


def _with_agent(document: MissionsDocument, code: str, record: AgentRecord) -> MissionsDocument:
    return MissionsDocument(
        schema_version=document.schema_version,
        agents={**document.agents, code: record},
    )


def _timestamp(now: datetime | None) -> datetime:
    moment = datetime.now().astimezone() if now is None else now
    if moment.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    return moment.replace(microsecond=0)


def _check_iterations(iterations: int) -> None:
    if type(iterations) is not int or iterations < 1:
        raise ValueError("kdf_iterations must be a positive integer")
