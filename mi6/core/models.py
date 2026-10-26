"""Immutable domain models and their JSON representation (plan, sections 2.2 and 2.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = 1
KDF_ALGORITHM = "pbkdf2_hmac_sha256"


class MissionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class KdfParams:
    """Key derivation settings of one agent. ``salt`` is standard Base64."""

    salt: str
    iterations: int
    algorithm: str = KDF_ALGORITHM

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "iterations": self.iterations,
            "salt": self.salt,
        }


@dataclass(frozen=True, slots=True)
class Mission:
    """One mission. Only ``report_token`` (a Fernet token) holds the encrypted report."""

    code_name: str
    threat_level: int
    status: MissionStatus
    created_at: datetime
    report_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", MissionStatus(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_name": self.code_name,
            "threat_level": self.threat_level,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "report_token": self.report_token,
        }


@dataclass(frozen=True, slots=True)
class AgentRecord:
    """All data stored for one agent code. ``missions`` keeps registration order."""

    kdf: KdfParams
    key_check: str
    missions: tuple[Mission, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "missions", tuple(self.missions))

    def find_mission(self, code_name: str) -> Mission | None:
        for mission in self.missions:
            if mission.code_name == code_name:
                return mission
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kdf": self.kdf.to_dict(),
            "key_check": self.key_check,
            "missions": [mission.to_dict() for mission in self.missions],
        }


@dataclass(frozen=True, slots=True)
class RiskReport:
    """Active missions of one agent, in registration order, and their global risk."""

    active_missions: tuple[Mission, ...]
    total: int
    level: RiskLevel

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_missions", tuple(self.active_missions))
        object.__setattr__(self, "level", RiskLevel(self.level))

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_missions": [mission.to_dict() for mission in self.active_missions],
            "total": self.total,
            "level": self.level.value,
        }


@dataclass(frozen=True, slots=True)
class MissionsDocument:
    """The whole ``missions.json`` file. ``agents`` maps agent codes to their records."""

    schema_version: int = SCHEMA_VERSION
    agents: Mapping[str, AgentRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "agents", MappingProxyType(dict(self.agents)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agents": {code: record.to_dict() for code, record in self.agents.items()},
        }
