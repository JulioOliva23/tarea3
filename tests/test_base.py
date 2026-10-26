"""Shared test base class and the tests that prove its isolation (constitution, principle 4)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

FIXED_NOW = datetime(2026, 10, 26, 14, 32, 7, tzinfo=timezone(timedelta(hours=1)))


class MI6TestCase(unittest.TestCase):
    """Base class for every test that may touch the file system.

    Each test gets a fresh temporary directory, a sandboxed home directory
    (``HOME`` and ``Path.home()`` both point inside it) and a fixed, timezone
    aware ``now``. ``data_dir`` is the sandboxed ``.mi6`` path and never exists
    when the test starts, so the real ``~/.mi6`` can never be reached.
    """

    def setUp(self) -> None:
        super().setUp()
        temp_dir = tempfile.TemporaryDirectory(prefix="mi6-test-")
        self.addCleanup(temp_dir.cleanup)
        self.tmp_path = Path(temp_dir.name).resolve()

        self.home = self.tmp_path / "home"
        self.home.mkdir(mode=0o700)
        self.data_dir = self.home / ".mi6"
        self.now = FIXED_NOW

        env_patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

        home_patcher = mock.patch.object(Path, "home", return_value=self.home)
        home_patcher.start()
        self.addCleanup(home_patcher.stop)


class MI6TestCaseIsolationTest(MI6TestCase):
    def test_data_dir_lives_inside_temporary_directory(self) -> None:
        self.assertTrue(self.data_dir.is_relative_to(self.tmp_path))
        self.assertEqual(self.data_dir.name, ".mi6")

    def test_data_dir_does_not_exist_at_start(self) -> None:
        self.assertFalse(self.data_dir.exists())

    def test_home_is_sandboxed(self) -> None:
        self.assertEqual(Path.home(), self.home)
        self.assertEqual(os.environ["HOME"], str(self.home))
        self.assertEqual(Path("~").expanduser(), self.home)
        self.assertEqual(Path.home() / ".mi6", self.data_dir)

    def test_now_is_fixed_and_timezone_aware(self) -> None:
        self.assertEqual(self.now, FIXED_NOW)
        self.assertIsNotNone(self.now.tzinfo)
        self.assertIsNotNone(self.now.utcoffset())


class MI6TestCaseLifecycleTest(unittest.TestCase):
    """Runs MI6TestCase by hand to check what happens before and after a test."""

    def _run_probe(self) -> tuple[unittest.TestResult, dict[str, object]]:
        seen: dict[str, object] = {}

        class Probe(MI6TestCase):
            def runTest(self) -> None:
                seen["tmp_path"] = self.tmp_path
                seen["home_during"] = Path.home()
                self.data_dir.mkdir(mode=0o700)
                (self.data_dir / "missions.json").write_text("{}", encoding="utf-8")

        result = unittest.TestResult()
        Probe().run(result)
        return result, seen

    def test_temporary_directory_is_removed_after_test(self) -> None:
        result, seen = self._run_probe()
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertFalse(Path(seen["tmp_path"]).exists())

    def test_home_is_restored_after_test(self) -> None:
        real_home = Path.home()
        real_env_home = os.environ.get("HOME")
        result, seen = self._run_probe()
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertNotEqual(seen["home_during"], real_home)
        self.assertEqual(Path.home(), real_home)
        self.assertEqual(os.environ.get("HOME"), real_env_home)

    def test_each_test_gets_its_own_directory(self) -> None:
        _, first = self._run_probe()
        _, second = self._run_probe()
        self.assertNotEqual(first["tmp_path"], second["tmp_path"])

    def test_real_data_dir_is_not_touched(self) -> None:
        real_data_dir = Path(os.path.expanduser("~")) / ".mi6"
        before = _snapshot(real_data_dir)
        result, _ = self._run_probe()
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertEqual(_snapshot(real_data_dir), before)


def _snapshot(path: Path) -> tuple[object, ...] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (info.st_ino, info.st_mode, info.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
