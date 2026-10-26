"""Tests for mi6.core.errors (plan, section 1, domain exceptions table)."""

from __future__ import annotations

import unittest
from pathlib import Path

from mi6.core import errors
from mi6.core.errors import (
    AuthenticationError,
    CorruptDataError,
    DataAccessError,
    DuplicateMissionError,
    InsecurePermissionsError,
    InvalidAgentCodeError,
    Mi6Error,
    MissionNotFoundError,
    OperationInProgressError,
    PasswordPolicyError,
    StorageError,
    SymlinkError,
    UnsafeEnvironmentError,
    ValidationError,
)
from mi6.core.models import MissionStatus

DATA_PATH = Path("/tmp/mi6-test/.mi6/missions.json")

# Exit code groups from the plan, section 4.7.
EXIT_1 = (ValidationError, AuthenticationError, DuplicateMissionError, MissionNotFoundError)
EXIT_3 = (StorageError,)


def sample_instances() -> list[Mi6Error]:
    return [
        ValidationError("report", "length", length=501),
        InvalidAgentCodeError(),
        PasswordPolicyError("too_short"),
        AuthenticationError(),
        DuplicateMissionError("SKYFALL", "active"),
        MissionNotFoundError("SKYFALL"),
        StorageError(DATA_PATH),
        DataAccessError(DATA_PATH, "EACCES"),
        InsecurePermissionsError(DATA_PATH, 0o644, 0o600),
        SymlinkError(DATA_PATH),
        CorruptDataError("invalid", path=DATA_PATH),
        OperationInProgressError(DATA_PATH),
        UnsafeEnvironmentError("root"),
    ]


class HierarchyTest(unittest.TestCase):
    def test_direct_parents(self) -> None:
        cases = [
            (Mi6Error, Exception),
            (ValidationError, Mi6Error),
            (InvalidAgentCodeError, ValidationError),
            (PasswordPolicyError, ValidationError),
            (AuthenticationError, Mi6Error),
            (DuplicateMissionError, Mi6Error),
            (MissionNotFoundError, Mi6Error),
            (StorageError, Mi6Error),
            (DataAccessError, StorageError),
            (InsecurePermissionsError, StorageError),
            (SymlinkError, StorageError),
            (CorruptDataError, StorageError),
            (OperationInProgressError, StorageError),
            (UnsafeEnvironmentError, StorageError),
        ]
        for cls, parent in cases:
            with self.subTest(cls=cls.__name__):
                self.assertIs(cls.__bases__[0], parent)
                self.assertEqual(len(cls.__bases__), 1)

    def test_every_error_is_a_mi6_error(self) -> None:
        for error in sample_instances():
            with self.subTest(error=type(error).__name__):
                self.assertIsInstance(error, Mi6Error)
                self.assertIsInstance(error, Exception)

    def test_exit_code_groups_do_not_overlap(self) -> None:
        for error in sample_instances():
            with self.subTest(error=type(error).__name__):
                self.assertNotEqual(isinstance(error, EXIT_1), isinstance(error, EXIT_3))

    def test_storage_errors_are_not_validation_errors(self) -> None:
        for cls in (DataAccessError, InsecurePermissionsError, SymlinkError, CorruptDataError,
                    OperationInProgressError, UnsafeEnvironmentError):
            with self.subTest(cls=cls.__name__):
                self.assertFalse(issubclass(cls, ValidationError))
                self.assertFalse(issubclass(cls, AuthenticationError))

    def test_not_os_errors(self) -> None:
        # Domain errors must never be swallowed by a generic `except OSError`.
        for error in sample_instances():
            with self.subTest(error=type(error).__name__):
                self.assertNotIsInstance(error, OSError)

    def test_errors_can_be_raised_and_caught_by_base(self) -> None:
        for error in sample_instances():
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(Mi6Error) as ctx:
                    raise error
                self.assertIs(ctx.exception, error)


class ValidationErrorAttributesTest(unittest.TestCase):
    def test_validation_error(self) -> None:
        error = ValidationError("code_name", "chars")
        self.assertEqual(error.field, "code_name")
        self.assertEqual(error.rule, "chars")
        self.assertIsNone(error.length)

    def test_validation_error_length(self) -> None:
        error = ValidationError("report", "length", length=501)
        self.assertEqual(error.length, 501)

    def test_length_is_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            ValidationError("report", "length", 501)  # type: ignore[misc]

    def test_invalid_agent_code(self) -> None:
        error = InvalidAgentCodeError()
        self.assertEqual((error.field, error.rule), ("agent_code", "format"))
        self.assertIsNone(error.length)

    def test_password_policy(self) -> None:
        for rule in ("too_short", "mismatch"):
            with self.subTest(rule=rule):
                error = PasswordPolicyError(rule)
                self.assertEqual((error.field, error.rule), ("password", rule))


class BusinessErrorAttributesTest(unittest.TestCase):
    def test_authentication_error_has_no_data(self) -> None:
        error = AuthenticationError()
        self.assertEqual(str(error), "authentication failed")

    def test_duplicate_mission(self) -> None:
        for status in ("active", MissionStatus.ARCHIVED):
            with self.subTest(status=status):
                error = DuplicateMissionError("SKYFALL", status)
                self.assertEqual(error.code_name, "SKYFALL")
                self.assertEqual(error.status, status)

    def test_duplicate_mission_accepts_status_enum(self) -> None:
        error = DuplicateMissionError("SPECTRE", MissionStatus.ARCHIVED)
        self.assertEqual(error.status, "archived")
        self.assertIn("archived", str(error))

    def test_mission_not_found(self) -> None:
        error = MissionNotFoundError("MOONRAKER")
        self.assertEqual(error.code_name, "MOONRAKER")


class StorageErrorAttributesTest(unittest.TestCase):
    def test_storage_error_path(self) -> None:
        self.assertIsNone(StorageError().path)
        self.assertEqual(StorageError(DATA_PATH).path, DATA_PATH)
        self.assertEqual(StorageError("/x/y").path, "/x/y")

    def test_data_access(self) -> None:
        error = DataAccessError(DATA_PATH, "ENOSPC")
        self.assertEqual(error.path, DATA_PATH)
        self.assertEqual(error.os_error_name, "ENOSPC")

    def test_insecure_permissions(self) -> None:
        error = InsecurePermissionsError(DATA_PATH.parent, 0o755, 0o700)
        self.assertEqual(error.path, DATA_PATH.parent)
        self.assertEqual(error.current_mode, 0o755)
        self.assertEqual(error.expected_mode, 0o700)
        self.assertIn("0755", str(error))
        self.assertIn("0700", str(error))

    def test_symlink(self) -> None:
        self.assertEqual(SymlinkError(DATA_PATH).path, DATA_PATH)

    def test_corrupt_data(self) -> None:
        for reason in ("incomplete", "unreadable", "invalid"):
            with self.subTest(reason=reason):
                error = CorruptDataError(reason)
                self.assertEqual(error.reason, reason)
                self.assertIsNone(error.path)
        self.assertEqual(CorruptDataError("invalid", path=DATA_PATH).path, DATA_PATH)

    def test_corrupt_data_path_is_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            CorruptDataError("invalid", DATA_PATH)  # type: ignore[misc]

    def test_operation_in_progress(self) -> None:
        self.assertIsNone(OperationInProgressError().path)
        self.assertEqual(OperationInProgressError(DATA_PATH).path, DATA_PATH)

    def test_unsafe_environment(self) -> None:
        for reason in ("root", "no_home"):
            with self.subTest(reason=reason):
                error = UnsafeEnvironmentError(reason)
                self.assertEqual(error.reason, reason)
                self.assertIsNone(error.path)


class NoAgentTextTest(unittest.TestCase):
    """Agent-facing Spanish text belongs to mi6/cli/messages.py (principle 6)."""

    def test_messages_are_plain_ascii(self) -> None:
        for error in sample_instances():
            with self.subTest(error=type(error).__name__):
                self.assertTrue(str(error).isascii(), str(error))

    def test_module_exports_only_exceptions(self) -> None:
        public = [name for name in vars(errors) if not name.startswith("_")]
        classes = [obj for name in public if isinstance(obj := getattr(errors, name), type)]
        self.assertTrue(all(issubclass(cls, Exception) for cls in classes))
        self.assertEqual(len(classes), 14)


if __name__ == "__main__":
    unittest.main()
