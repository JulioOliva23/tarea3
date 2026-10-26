"""Tests for mi6.core.storage (RF-4.6, RF-6.1 to RF-6.9, RNF-2; plan, sections 2.5, 2.6 and D4)."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from pathlib import Path
from unittest import mock

from mi6.core import storage
from mi6.core.errors import (
    CorruptDataError,
    DataAccessError,
    InsecurePermissionsError,
    OperationInProgressError,
    SymlinkError,
    UnsafeEnvironmentError,
)
from tests.test_base import IS_ROOT, MI6TestCase, skip_if_root

SAMPLE = {"schema_version": 1, "agents": {"007": {"note": "Ñandú 🦩"}}}


class StorageTestCase(MI6TestCase):
    def make_data_dir(self, *, with_lock: bool = True, document: object = SAMPLE) -> None:
        self.data_dir.mkdir()
        os.chmod(self.data_dir, 0o700)
        if with_lock:
            self.lock_file.touch()
            os.chmod(self.lock_file, 0o600)
        if document is not None:
            self.missions_file.write_text(json.dumps(document), encoding="utf-8")
            os.chmod(self.missions_file, 0o600)

    def temp_files(self) -> list[str]:
        return [name for name in os.listdir(self.data_dir) if name.startswith(storage.TEMP_PREFIX)]


class ConstantsTest(StorageTestCase):
    def test_values(self) -> None:
        self.assertEqual(storage.DATA_DIR_NAME, ".mi6")
        self.assertEqual(storage.MISSIONS_FILE, "missions.json")
        self.assertEqual(storage.LOCK_FILE, "missions.lock")
        self.assertEqual(storage.TEMP_PREFIX, ".missions.json.tmp-")
        self.assertEqual(storage.DIR_MODE, 0o700)
        self.assertEqual(storage.FILE_MODE, 0o600)

    def test_paths(self) -> None:
        self.assertEqual(storage.missions_path(self.data_dir), self.missions_file)
        self.assertEqual(storage.lock_path(str(self.data_dir)), self.lock_file)


class ResolveDataDirTest(StorageTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.resolve = self.unguarded_resolve_data_dir

    def test_returns_home_mi6(self) -> None:
        with mock.patch("mi6.core.storage.os.geteuid", return_value=1000):
            self.assertEqual(self.resolve(), self.home / ".mi6")
        self.assertFalse(self.data_dir.exists())

    def test_rejects_root(self) -> None:
        with mock.patch("mi6.core.storage.os.geteuid", return_value=0):
            with self.assertRaises(UnsafeEnvironmentError) as ctx:
                self.resolve()
        self.assertEqual(ctx.exception.reason, "root")

    def test_root_is_checked_before_home(self) -> None:
        with mock.patch("mi6.core.storage.os.geteuid", return_value=0), \
                mock.patch.object(Path, "home", side_effect=RuntimeError):
            with self.assertRaises(UnsafeEnvironmentError) as ctx:
                self.resolve()
        self.assertEqual(ctx.exception.reason, "root")

    def test_rejects_missing_home(self) -> None:
        for error in (RuntimeError("no home"), KeyError("HOME"), OSError("broken")):
            with self.subTest(error=type(error).__name__):
                with mock.patch("mi6.core.storage.os.geteuid", return_value=1000), \
                        mock.patch.object(Path, "home", side_effect=error):
                    with self.assertRaises(UnsafeEnvironmentError) as ctx:
                        self.resolve()
                self.assertEqual(ctx.exception.reason, "no_home")

    def test_rejects_relative_home(self) -> None:
        for home in (Path("relative/home"), Path("")):
            with self.subTest(home=str(home)):
                with mock.patch("mi6.core.storage.os.geteuid", return_value=1000), \
                        mock.patch.object(Path, "home", return_value=home):
                    with self.assertRaises(UnsafeEnvironmentError) as ctx:
                        self.resolve()
                self.assertEqual(ctx.exception.reason, "no_home")


class DataDirExistsTest(StorageTestCase):
    def test_missing(self) -> None:
        self.assertFalse(storage.data_dir_exists(self.data_dir))

    def test_present(self) -> None:
        self.make_data_dir()
        self.assertTrue(storage.data_dir_exists(self.data_dir))

    def test_dangling_symlink_counts_as_existing(self) -> None:
        os.symlink(self.tmp_path / "nowhere", self.data_dir)
        self.assertTrue(storage.data_dir_exists(self.data_dir))


class CheckNoSymlinksTest(StorageTestCase):
    def test_missing_data_dir_is_fine(self) -> None:
        storage.check_no_symlinks(self.data_dir)

    def test_regular_layout_is_fine(self) -> None:
        self.make_data_dir()
        storage.check_no_symlinks(self.data_dir)

    def test_symlinked_data_dir(self) -> None:
        real = self.tmp_path / "real"
        real.mkdir(mode=0o700)
        os.symlink(real, self.data_dir)
        with self.assertRaises(SymlinkError) as ctx:
            storage.check_no_symlinks(self.data_dir)
        self.assertEqual(ctx.exception.path, self.data_dir)

    def test_symlinked_files(self) -> None:
        for target in (self.missions_file, self.lock_file):
            with self.subTest(file=target.name):
                self.make_data_dir()
                elsewhere = self.tmp_path / f"elsewhere-{target.name}"
                os.replace(target, elsewhere)
                os.symlink(elsewhere, target)
                with self.assertRaises(SymlinkError) as ctx:
                    storage.check_no_symlinks(self.data_dir)
                self.assertEqual(ctx.exception.path, target)
                target.unlink()
                elsewhere.unlink()
                for child in self.data_dir.iterdir():
                    child.unlink()
                self.data_dir.rmdir()

    def test_data_dir_that_is_a_file(self) -> None:
        self.data_dir.write_text("not a directory")
        with self.assertRaises(DataAccessError) as ctx:
            storage.check_no_symlinks(self.data_dir)
        self.assertEqual(ctx.exception.os_error_name, "ENOTDIR")


@skip_if_root
class CheckPermissionsTest(StorageTestCase):
    def test_secure_layout_is_fine(self) -> None:
        self.make_data_dir()
        storage.check_permissions(self.data_dir)

    def test_missing_data_dir_is_fine(self) -> None:
        storage.check_permissions(self.data_dir)

    def test_open_modes_are_rejected_and_not_fixed(self) -> None:
        cases = [
            ("data_dir", 0o755, 0o700),
            ("data_dir", 0o710, 0o700),
            ("data_dir", 0o701, 0o700),
            ("missions", 0o644, 0o600),
            ("missions", 0o660, 0o600),
            ("missions", 0o604, 0o600),
            ("lock", 0o640, 0o600),
            ("lock", 0o666, 0o600),
        ]
        for target_name, mode, expected in cases:
            with self.subTest(target=target_name, mode=oct(mode)):
                self.make_data_dir()
                target = {"data_dir": self.data_dir, "missions": self.missions_file, "lock": self.lock_file}[target_name]
                os.chmod(target, mode)
                with self.assertRaises(InsecurePermissionsError) as ctx:
                    storage.check_permissions(self.data_dir)
                self.assertEqual(ctx.exception.path, target)
                self.assertEqual(ctx.exception.current_mode, mode)
                self.assertEqual(ctx.exception.expected_mode, expected)
                self.assertEqual(self.mode_of(target), mode)
                os.chmod(self.data_dir, 0o700)
                for child in self.data_dir.iterdir():
                    child.unlink()
                self.data_dir.rmdir()

    def test_foreign_owner_is_rejected(self) -> None:
        self.make_data_dir()
        with mock.patch("mi6.core.storage.os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(InsecurePermissionsError) as ctx:
                storage.check_permissions(self.data_dir)
        self.assertEqual(ctx.exception.path, self.data_dir)
        self.assertEqual(ctx.exception.current_mode, 0o700)

    def test_non_regular_missions_file_is_corrupt(self) -> None:
        self.make_data_dir(document=None)
        self.missions_file.mkdir(mode=0o700)
        with self.assertRaises(CorruptDataError) as ctx:
            storage.check_permissions(self.data_dir)
        self.assertEqual(ctx.exception.reason, "invalid")


class CheckNoRemnantsTest(StorageTestCase):
    def test_missing_data_dir_is_fine(self) -> None:
        storage.check_no_remnants(self.data_dir)

    def test_complete_layout_is_fine(self) -> None:
        self.make_data_dir()
        storage.check_no_remnants(self.data_dir)

    def test_empty_data_dir(self) -> None:
        self.make_data_dir(with_lock=False, document=None)
        with self.assertRaises(CorruptDataError) as ctx:
            storage.check_no_remnants(self.data_dir)
        self.assertEqual(ctx.exception.reason, "incomplete")

    def test_missing_missions_file(self) -> None:
        self.make_data_dir(document=None)
        with self.assertRaises(CorruptDataError) as ctx:
            storage.check_no_remnants(self.data_dir)
        self.assertEqual((ctx.exception.reason, ctx.exception.path), ("incomplete", self.missions_file))

    def test_missing_lock_file(self) -> None:
        self.make_data_dir(with_lock=False)
        with self.assertRaises(CorruptDataError) as ctx:
            storage.check_no_remnants(self.data_dir)
        self.assertEqual((ctx.exception.reason, ctx.exception.path), ("incomplete", self.lock_file))

    def test_orphan_temporary_file(self) -> None:
        self.make_data_dir()
        orphan = self.data_dir / ".missions.json.tmp-abc123"
        orphan.write_text("{")
        with self.assertRaises(CorruptDataError) as ctx:
            storage.check_no_remnants(self.data_dir)
        self.assertEqual((ctx.exception.reason, ctx.exception.path), ("incomplete", orphan))


class InitializeDataDirTest(StorageTestCase):
    def test_creates_private_dir_and_lock_even_with_open_umask(self) -> None:
        self.set_umask(0o000)
        storage.initialize_data_dir(self.data_dir)
        self.assertEqual(self.mode_of(self.data_dir), 0o700)
        self.assertEqual(self.mode_of(self.lock_file), 0o600)
        self.assertEqual(self.lock_file.read_bytes(), b"")
        self.assertFalse(self.missions_file.exists())

    def test_existing_dir_means_another_execution(self) -> None:
        self.make_data_dir()
        before = self.snapshot_dir()
        with self.assertRaises(OperationInProgressError):
            storage.initialize_data_dir(self.data_dir)
        self.assertEqual(self.snapshot_dir(), before)

    def test_missing_parent_is_a_data_access_error(self) -> None:
        with self.assertRaises(DataAccessError) as ctx:
            storage.initialize_data_dir(self.tmp_path / "missing" / ".mi6")
        self.assertEqual(ctx.exception.os_error_name, "ENOENT")

    def test_rolls_back_when_lock_creation_fails(self) -> None:
        real_open = os.open

        def failing_open(path, flags, *args):
            if Path(path) == self.lock_file:
                raise PermissionError(13, "denied")
            return real_open(path, flags, *args)

        with mock.patch("mi6.core.storage.os.open", side_effect=failing_open):
            with self.assertRaises(DataAccessError) as ctx:
                storage.initialize_data_dir(self.data_dir)
        self.assertEqual(ctx.exception.os_error_name, "EACCES")
        self.assertFalse(self.data_dir.exists())


class DiscardUninitializedDataDirTest(StorageTestCase):
    def test_removes_freshly_initialized_dir(self) -> None:
        storage.initialize_data_dir(self.data_dir)
        storage.discard_uninitialized_data_dir(self.data_dir)
        self.assertFalse(self.data_dir.exists())

    def test_never_removes_real_data(self) -> None:
        self.make_data_dir()
        before = self.snapshot_dir()
        storage.discard_uninitialized_data_dir(self.data_dir)
        self.assertEqual(self.snapshot_dir(), before)


class LockTest(StorageTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_data_dir()

    def test_exclusive_lock_is_really_held(self) -> None:
        with storage.exclusive_lock(self.data_dir):
            fd = os.open(self.lock_file, os.O_RDONLY)
            self.addCleanup(os.close, fd)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def test_shared_locks_coexist(self) -> None:
        self.hold_lock(fcntl.LOCK_SH)
        with storage.shared_lock(self.data_dir):
            with storage.shared_lock(self.data_dir):
                pass

    def test_exclusive_fails_immediately_on_contention(self) -> None:
        for held in (fcntl.LOCK_EX, fcntl.LOCK_SH):
            with self.subTest(held=held):
                fd = os.open(self.lock_file, os.O_RDWR)
                fcntl.flock(fd, held | fcntl.LOCK_NB)
                try:
                    with self.assertRaises(OperationInProgressError) as ctx:
                        with storage.exclusive_lock(self.data_dir):
                            self.fail("lock should not be acquired")
                    self.assertEqual(ctx.exception.path, self.lock_file)
                finally:
                    os.close(fd)

    def test_shared_fails_immediately_against_exclusive(self) -> None:
        self.hold_lock(fcntl.LOCK_EX)
        with self.assertRaises(OperationInProgressError):
            with storage.shared_lock(self.data_dir):
                self.fail("lock should not be acquired")

    def test_lock_is_released_after_exception(self) -> None:
        with self.assertRaises(RuntimeError):
            with storage.exclusive_lock(self.data_dir):
                raise RuntimeError("boom")
        with storage.exclusive_lock(self.data_dir):
            pass

    def test_lock_is_released_after_keyboard_interrupt(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            with storage.exclusive_lock(self.data_dir):
                raise KeyboardInterrupt
        self.hold_lock(fcntl.LOCK_EX)

    def test_generic_file_lock_accepts_only_sh_or_ex(self) -> None:
        with storage.file_lock(self.data_dir, fcntl.LOCK_SH):
            pass
        with storage.file_lock(self.data_dir, fcntl.LOCK_EX):
            pass
        for operation in (fcntl.LOCK_UN, fcntl.LOCK_EX | fcntl.LOCK_NB, 0):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    with storage.file_lock(self.data_dir, operation):
                        pass

    def test_missing_lock_file_is_never_created(self) -> None:
        self.lock_file.unlink()
        for lock in (storage.shared_lock, storage.exclusive_lock):
            with self.subTest(lock=lock.__name__):
                with self.assertRaises(CorruptDataError) as ctx:
                    with lock(self.data_dir):
                        pass
                self.assertEqual(ctx.exception.reason, "incomplete")
                self.assertFalse(self.lock_file.exists())

    def test_symlinked_lock_file_is_not_followed(self) -> None:
        target = self.tmp_path / "other.lock"
        target.touch()
        self.lock_file.unlink()
        os.symlink(target, self.lock_file)
        with self.assertRaises(SymlinkError):
            with storage.exclusive_lock(self.data_dir):
                pass


class ReadDocumentTest(StorageTestCase):
    def test_reads_utf8_json(self) -> None:
        self.make_data_dir()
        self.assertEqual(storage.read_document(self.data_dir), SAMPLE)

    def test_unreadable_content(self) -> None:
        cases = {
            "invalid json": b"{not json",
            "truncated": b'{"schema_version": 1',
            "empty": b"",
            "not utf-8": b'{"a": "\xff"}',
            "duplicate keys": b'{"agents": {}, "agents": {}}',
            "nan": b'{"x": NaN}',
            "infinity": b'{"x": -Infinity}',
        }
        for name, content in cases.items():
            with self.subTest(case=name):
                if not self.data_dir.exists():
                    self.make_data_dir(document=None)
                self.missions_file.write_bytes(content)
                with self.assertRaises(CorruptDataError) as ctx:
                    storage.read_document(self.data_dir)
                self.assertEqual((ctx.exception.reason, ctx.exception.path), ("unreadable", self.missions_file))

    def test_valid_json_of_any_shape_is_returned_unvalidated(self) -> None:
        self.make_data_dir(document=[1, 2, 3])
        self.assertEqual(storage.read_document(self.data_dir), [1, 2, 3])

    def test_missing_file_is_incomplete(self) -> None:
        self.make_data_dir(document=None)
        with self.assertRaises(CorruptDataError) as ctx:
            storage.read_document(self.data_dir)
        self.assertEqual(ctx.exception.reason, "incomplete")

    def test_symlink_is_not_followed(self) -> None:
        self.make_data_dir(document=None)
        target = self.tmp_path / "elsewhere.json"
        target.write_text(json.dumps(SAMPLE))
        os.symlink(target, self.missions_file)
        with self.assertRaises(SymlinkError):
            storage.read_document(self.data_dir)

    @skip_if_root
    def test_permission_denied_is_data_access_error(self) -> None:
        self.make_data_dir()
        os.chmod(self.missions_file, 0o000)
        with self.assertRaises(DataAccessError) as ctx:
            storage.read_document(self.data_dir)
        self.assertEqual(ctx.exception.os_error_name, "EACCES")


class WriteDocumentAtomicTest(StorageTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_data_dir(document={"previous": True})
        self.original = self.missions_file.read_bytes()

    def test_writes_utf8_json_and_leaves_no_temporary(self) -> None:
        storage.write_document_atomic(self.data_dir, SAMPLE)
        content = self.missions_file.read_bytes()
        self.assertEqual(json.loads(content.decode("utf-8")), SAMPLE)
        self.assertIn("Ñandú 🦩".encode("utf-8"), content)
        self.assertTrue(content.endswith(b"\n"))
        self.assertEqual(self.temp_files(), [])

    def test_result_is_0600_whatever_the_umask(self) -> None:
        for mask in (0o000, 0o022, 0o077, 0o277):
            with self.subTest(umask=oct(mask)):
                self.set_umask(mask)
                storage.write_document_atomic(self.data_dir, SAMPLE)
                self.assertEqual(self.mode_of(self.missions_file), 0o600)

    def test_replaces_inode_atomically(self) -> None:
        before = os.stat(self.missions_file).st_ino
        storage.write_document_atomic(self.data_dir, SAMPLE)
        self.assertNotEqual(os.stat(self.missions_file).st_ino, before)

    def test_temporary_file_is_0600_in_same_directory(self) -> None:
        seen = {}
        real_replace = os.replace

        def spy_replace(src, dst):
            seen["dir"] = Path(src).parent
            seen["name"] = Path(src).name
            seen["mode"] = stat.S_IMODE(os.stat(src).st_mode)
            return real_replace(src, dst)

        self.set_umask(0o000)
        with mock.patch("mi6.core.storage.os.replace", side_effect=spy_replace):
            storage.write_document_atomic(self.data_dir, SAMPLE)
        self.assertEqual(seen["dir"], self.data_dir)
        self.assertTrue(seen["name"].startswith(storage.TEMP_PREFIX))
        self.assertEqual(seen["mode"], 0o600)

    def test_content_is_fsynced_before_rename(self) -> None:
        calls = []
        real_fsync, real_replace = os.fsync, os.replace
        with mock.patch("mi6.core.storage.os.fsync", side_effect=lambda fd: (calls.append("fsync"), real_fsync(fd))), \
                mock.patch("mi6.core.storage.os.replace",
                           side_effect=lambda s, d: (calls.append("replace"), real_replace(s, d))):
            storage.write_document_atomic(self.data_dir, SAMPLE)
        self.assertEqual(calls, ["fsync", "replace", "fsync"])

    def test_os_error_on_replace_keeps_original(self) -> None:
        with mock.patch("mi6.core.storage.os.replace", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(DataAccessError) as ctx:
                storage.write_document_atomic(self.data_dir, SAMPLE)
        self.assertEqual(ctx.exception.os_error_name, "ENOSPC")
        self.assertEqual(self.missions_file.read_bytes(), self.original)
        self.assertEqual(self.temp_files(), [])

    def test_keyboard_interrupt_keeps_original(self) -> None:
        for target in ("mi6.core.storage.os.replace", "mi6.core.storage.os.fsync"):
            with self.subTest(interrupted=target):
                with mock.patch(target, side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        storage.write_document_atomic(self.data_dir, SAMPLE)
                self.assertEqual(self.missions_file.read_bytes(), self.original)
                self.assertEqual(self.temp_files(), [])

    def test_unserializable_document_keeps_original(self) -> None:
        with self.assertRaises(TypeError):
            storage.write_document_atomic(self.data_dir, {"bad": object()})
        self.assertEqual(self.missions_file.read_bytes(), self.original)
        self.assertEqual(self.temp_files(), [])

    def test_missing_directory_is_data_access_error(self) -> None:
        with self.assertRaises(DataAccessError):
            storage.write_document_atomic(self.tmp_path / "missing", SAMPLE)

    @skip_if_root
    def test_read_only_directory_is_data_access_error(self) -> None:
        os.chmod(self.data_dir, 0o500)
        self.addCleanup(os.chmod, self.data_dir, 0o700)
        with self.assertRaises(DataAccessError) as ctx:
            storage.write_document_atomic(self.data_dir, SAMPLE)
        self.assertEqual(ctx.exception.os_error_name, "EACCES")
        self.assertEqual(self.missions_file.read_bytes(), self.original)


class EnvironmentAssumptionsTest(StorageTestCase):
    def test_not_running_as_root(self) -> None:
        if IS_ROOT:
            self.skipTest("permission tests are skipped as root")
        self.assertNotEqual(os.geteuid(), 0)
