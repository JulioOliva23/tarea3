"""Domain exceptions raised by mi6.core.

Exceptions carry structured data only (field, rule, path, modes, reason...).
Turning them into agent-facing text and exit codes is the job of mi6.cli.
"""

from __future__ import annotations

import os


class Mi6Error(Exception):
    """Base class for every domain error."""


class ValidationError(Mi6Error):
    """An input does not satisfy a format rule.

    ``length`` is only set when the rule is ``"length"``, so the CLI can
    report the offending size without the core ever echoing the input.
    """

    def __init__(self, field: str, rule: str, *, length: int | None = None) -> None:
        super().__init__(f"{field}: {rule}")
        self.field = field
        self.rule = rule
        self.length = length


class InvalidAgentCodeError(ValidationError):
    """The agent code is not one of 001 to 009 (RF-1.2)."""

    def __init__(self) -> None:
        super().__init__("agent_code", "format")


class PasswordPolicyError(ValidationError):
    """A new password is rejected (RF-2.4). ``rule`` is ``too_short`` or ``mismatch``."""

    def __init__(self, rule: str) -> None:
        super().__init__("password", rule)


class AuthenticationError(Mi6Error):
    """The password does not unlock the agent's data (RF-2.6)."""

    def __init__(self) -> None:
        super().__init__("authentication failed")


class DuplicateMissionError(Mi6Error):
    """The agent already has a mission with this code name (RF-3.10)."""

    def __init__(self, code_name: str, status: str) -> None:
        super().__init__(f"duplicate mission {code_name} ({status})")
        self.code_name = code_name
        self.status = status


class MissionNotFoundError(Mi6Error):
    """The code name is not among the agent's active missions (RF-5.4)."""

    def __init__(self, code_name: str) -> None:
        super().__init__(f"active mission not found: {code_name}")
        self.code_name = code_name


class StorageError(Mi6Error):
    """Base class for data, permission and environment failures."""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        detail: str = "storage failure",
    ) -> None:
        super().__init__(detail if path is None else f"{detail}: {os.fspath(path)}")
        self.path = path


class DataAccessError(StorageError):
    """Local data cannot be read or written (RF-6.1).

    ``os_error_name`` is the symbolic errno (for example ``EACCES``).
    """

    def __init__(self, path: str | os.PathLike[str], os_error_name: str) -> None:
        super().__init__(path, f"data access failed ({os_error_name})")
        self.os_error_name = os_error_name


class InsecurePermissionsError(StorageError):
    """The data directory or a data file is open to group or others (RF-6.2)."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        current_mode: int,
        expected_mode: int,
    ) -> None:
        super().__init__(
            path,
            f"insecure permissions {current_mode:04o}, expected {expected_mode:04o}",
        )
        self.current_mode = current_mode
        self.expected_mode = expected_mode


class SymlinkError(StorageError):
    """The data path contains a symbolic link (RF-6.3)."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        super().__init__(path, "symbolic link in data path")


class CorruptDataError(StorageError):
    """Stored data is unusable (RF-6.5, RF-6.7).

    ``reason`` is ``incomplete``, ``unreadable`` or ``invalid``.
    """

    def __init__(self, reason: str, *, path: str | os.PathLike[str] | None = None) -> None:
        super().__init__(path, f"corrupt data ({reason})")
        self.reason = reason


class OperationInProgressError(StorageError):
    """Another process holds the data lock (RF-6.8)."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        super().__init__(path, "operation in progress")


class UnsafeEnvironmentError(StorageError):
    """The process environment is not safe to run in (RF-6.9).

    ``reason`` is ``root`` or ``no_home``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(None, f"unsafe environment ({reason})")
        self.reason = reason
