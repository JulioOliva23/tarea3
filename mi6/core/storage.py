"""Local data directory: location, safety checks, locking and atomic writes.

Covers RF-4.6, RF-6.1 to RF-6.9 and RNF-2 (plan, sections 2.1, 2.5, 2.6 and D4).
Every function receives ``data_dir`` explicitly; only the CLI calls
``resolve_data_dir`` to obtain the real ``~/.mi6``.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

from mi6.core.errors import (
    CorruptDataError,
    DataAccessError,
    InsecurePermissionsError,
    OperationInProgressError,
    SymlinkError,
    UnsafeEnvironmentError,
)

DATA_DIR_NAME = ".mi6"
MISSIONS_FILE = "missions.json"
LOCK_FILE = "missions.lock"
TEMP_PREFIX = ".missions.json.tmp-"
DIR_MODE = 0o700
FILE_MODE = 0o600

_GROUP_OTHER_BITS = 0o077
_OPEN_FLAGS = os.O_NOFOLLOW | os.O_CLOEXEC

DataDir = str | os.PathLike[str]


def resolve_data_dir() -> Path:
    """Return ``~/.mi6`` after checking the process environment (RF-6.9)."""
    if os.geteuid() == 0:
        raise UnsafeEnvironmentError("root")
    try:
        home = Path.home()
    except (RuntimeError, KeyError, OSError) as exc:
        raise UnsafeEnvironmentError("no_home") from exc
    if not home.is_absolute():
        raise UnsafeEnvironmentError("no_home")
    return home / DATA_DIR_NAME


def missions_path(data_dir: DataDir) -> Path:
    return Path(data_dir) / MISSIONS_FILE


def lock_path(data_dir: DataDir) -> Path:
    return Path(data_dir) / LOCK_FILE


def data_dir_exists(data_dir: DataDir) -> bool:
    """True if anything, even a dangling symlink, exists at ``data_dir``."""
    return os.path.lexists(data_dir)


def check_no_symlinks(data_dir: DataDir) -> None:
    """Raise SymlinkError if the data dir, missions.json or missions.lock is a symlink (RF-6.3)."""
    data_dir = Path(data_dir)
    info = _lstat(data_dir)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        raise SymlinkError(data_dir)
    if not stat.S_ISDIR(info.st_mode):
        raise DataAccessError(data_dir, "ENOTDIR")
    for path in (missions_path(data_dir), lock_path(data_dir)):
        info = _lstat(path)
        if info is not None and stat.S_ISLNK(info.st_mode):
            raise SymlinkError(path)


def check_permissions(data_dir: DataDir) -> None:
    """Raise InsecurePermissionsError if group or others have any access, or the owner differs.

    Expected modes are 0700 for the directory and 0600 for the files (RF-6.2).
    Permissions are only inspected, never changed.
    """
    data_dir = Path(data_dir)
    targets = (
        (data_dir, DIR_MODE, stat.S_ISDIR),
        (missions_path(data_dir), FILE_MODE, stat.S_ISREG),
        (lock_path(data_dir), FILE_MODE, stat.S_ISREG),
    )
    for path, expected_mode, has_expected_type in targets:
        info = _lstat(path)
        if info is None:
            continue
        if not has_expected_type(info.st_mode):
            if path == data_dir:
                raise DataAccessError(path, "ENOTDIR")
            raise CorruptDataError("invalid", path=path)
        current_mode = stat.S_IMODE(info.st_mode)
        if current_mode & _GROUP_OTHER_BITS or info.st_uid != os.geteuid():
            raise InsecurePermissionsError(path, current_mode, expected_mode)


def check_no_remnants(data_dir: DataDir) -> None:
    """Raise CorruptDataError("incomplete") for a half-initialized or half-written data dir (RF-6.7).

    Must be called with the lock held, so another process's write in progress
    is never mistaken for a remnant.
    """
    data_dir = Path(data_dir)
    if not data_dir_exists(data_dir):
        return
    for path in (lock_path(data_dir), missions_path(data_dir)):
        if _lstat(path) is None:
            raise CorruptDataError("incomplete", path=path)
    try:
        names = os.listdir(data_dir)
    except OSError as exc:
        raise DataAccessError(data_dir, _errno_name(exc)) from exc
    for name in sorted(names):
        if name.startswith(TEMP_PREFIX):
            raise CorruptDataError("incomplete", path=data_dir / name)


def initialize_data_dir(data_dir: DataDir) -> None:
    """First use (RF-6.6): create the directory with 0700 and an empty lock file with 0600.

    missions.json is not created here. If the directory appears concurrently,
    another execution is initializing it and OperationInProgressError is raised.
    """
    data_dir = Path(data_dir)
    try:
        os.mkdir(data_dir, DIR_MODE)
    except FileExistsError as exc:
        raise OperationInProgressError(data_dir) from exc
    except OSError as exc:
        raise DataAccessError(data_dir, _errno_name(exc)) from exc
    try:
        os.chmod(data_dir, DIR_MODE)
        fd = os.open(lock_path(data_dir), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _OPEN_FLAGS, FILE_MODE)
        try:
            os.fchmod(fd, FILE_MODE)
        finally:
            os.close(fd)
    except BaseException as exc:
        _unlink_quietly(lock_path(data_dir))
        _rmdir_quietly(data_dir)
        if isinstance(exc, OSError):
            raise DataAccessError(data_dir, _errno_name(exc)) from exc
        raise


def discard_uninitialized_data_dir(data_dir: DataDir) -> None:
    """Undo initialize_data_dir when the first write never happened.

    Does nothing once missions.json exists, so real data is never removed.
    """
    data_dir = Path(data_dir)
    if _lstat(missions_path(data_dir)) is not None:
        return
    _unlink_quietly(lock_path(data_dir))
    _rmdir_quietly(data_dir)


@contextmanager
def file_lock(data_dir: DataDir, operation: int) -> Iterator[None]:
    """Hold ``fcntl.LOCK_SH`` or ``fcntl.LOCK_EX`` on missions.lock, never waiting (RF-6.8).

    The lock file is never created here: if it is missing the data dir is
    incomplete (RF-6.7). Contention raises OperationInProgressError at once.
    """
    if operation not in (fcntl.LOCK_SH, fcntl.LOCK_EX):
        raise ValueError("operation must be fcntl.LOCK_SH or fcntl.LOCK_EX")
    path = lock_path(data_dir)
    access = os.O_RDONLY if operation == fcntl.LOCK_SH else os.O_RDWR
    fd = _open_no_follow(path, access)
    try:
        try:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OperationInProgressError(path) from exc
        except OSError as exc:
            raise DataAccessError(path, _errno_name(exc)) from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def exclusive_lock(data_dir: DataDir) -> AbstractContextManager[None]:
    """Lock used by create and archive."""
    return file_lock(data_dir, fcntl.LOCK_EX)


def shared_lock(data_dir: DataDir) -> AbstractContextManager[None]:
    """Lock used by list and the lock-free pre-checks."""
    return file_lock(data_dir, fcntl.LOCK_SH)


def read_document(data_dir: DataDir) -> Any:
    """Return the raw, unvalidated JSON content of missions.json.

    Unparseable content (invalid UTF-8 or JSON, duplicate keys, NaN or
    Infinity) raises CorruptDataError("unreadable"); I/O errors raise
    DataAccessError.
    """
    path = missions_path(data_dir)
    fd = _open_no_follow(path, os.O_RDONLY)
    try:
        with os.fdopen(fd, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise DataAccessError(path, _errno_name(exc)) from exc
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise CorruptDataError("unreadable", path=path) from exc


def write_document_atomic(data_dir: DataDir, document: Mapping[str, Any]) -> None:
    """Replace missions.json atomically (plan, section 2.5; RNF-2).

    The content goes to a 0600 temporary file in the same directory, is
    fsynced and then renamed over missions.json with os.replace. On any
    failure, including KeyboardInterrupt, the temporary file is removed and
    the previous missions.json stays untouched.
    """
    data_dir = Path(data_dir)
    target = missions_path(data_dir)
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        fd, temp_name = tempfile.mkstemp(dir=data_dir, prefix=TEMP_PREFIX)
    except OSError as exc:
        raise DataAccessError(data_dir, _errno_name(exc)) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), FILE_MODE)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException as exc:
        _unlink_quietly(Path(temp_name))
        if isinstance(exc, OSError):
            raise DataAccessError(target, _errno_name(exc)) from exc
        raise
    _fsync_directory(data_dir)


def _open_no_follow(path: Path, access: int) -> int:
    try:
        return os.open(path, access | _OPEN_FLAGS)
    except FileNotFoundError as exc:
        raise CorruptDataError("incomplete", path=path) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SymlinkError(path) from exc
        raise DataAccessError(path, _errno_name(exc)) from exc


def _fsync_directory(data_dir: Path) -> None:
    try:
        fd = os.open(data_dir, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise DataAccessError(data_dir, _errno_name(exc)) from exc


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DataAccessError(path, _errno_name(exc)) from exc


def _unlink_quietly(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _rmdir_quietly(path: Path) -> None:
    try:
        os.rmdir(path)
    except OSError:
        pass


def _errno_name(exc: OSError) -> str:
    if exc.errno is None:
        return type(exc).__name__
    return errno.errorcode.get(exc.errno, type(exc).__name__)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {name}")
