"""Tests for mi6.core.risk (RF-4.3, RF-4.4, RF-4.5, RF-5.3; plan, section 3)."""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from mi6.core import risk
from mi6.core.models import Mission, MissionStatus, RiskLevel, RiskReport
from mi6.core.risk import compute_risk

BASE_TIME = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)


def make_mission(
    code_name: str,
    threat_level: int,
    status: MissionStatus = MissionStatus.ACTIVE,
    minute: int = 0,
) -> Mission:
    return Mission(
        code_name=code_name,
        threat_level=threat_level,
        status=status,
        created_at=BASE_TIME + timedelta(minutes=minute),
        report_token="gAAAAAB-token",
    )


def missions_with_total(total: int) -> list[Mission]:
    levels = [5] * (total // 5) + ([total % 5] if total % 5 else [])
    return [make_mission(f"M{index}", level, minute=index) for index, level in enumerate(levels)]


class ConstantsTest(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual(risk.LOW_MAX, 5)
        self.assertEqual(risk.MEDIUM_MAX, 10)


class ComputeRiskThresholdsTest(unittest.TestCase):
    def test_boundaries(self) -> None:
        cases = [
            (0, RiskLevel.LOW),
            (5, RiskLevel.LOW),
            (6, RiskLevel.MEDIUM),
            (10, RiskLevel.MEDIUM),
            (11, RiskLevel.CRITICAL),
        ]
        for total, expected in cases:
            with self.subTest(total=total):
                report = compute_risk(missions_with_total(total))
                self.assertEqual(report.total, total)
                self.assertIs(report.level, expected)

    def test_every_total_from_0_to_25(self) -> None:
        for total in range(26):
            expected = (
                RiskLevel.LOW if total <= 5
                else RiskLevel.MEDIUM if total <= 10
                else RiskLevel.CRITICAL
            )
            with self.subTest(total=total):
                self.assertIs(compute_risk(missions_with_total(total)).level, expected)

    def test_empty_list_is_zero_low(self) -> None:
        report = compute_risk([])
        self.assertEqual(report, RiskReport(active_missions=(), total=0, level=RiskLevel.LOW))

    def test_single_mission_levels(self) -> None:
        for level in range(1, 6):
            with self.subTest(level=level):
                report = compute_risk([make_mission("SOLO", level)])
                self.assertEqual(report.total, level)
                self.assertIs(report.level, RiskLevel.LOW)


class ComputeRiskArchivedTest(unittest.TestCase):
    def test_only_archived_is_zero_low(self) -> None:
        missions = [
            make_mission("SPECTRE", 5, MissionStatus.ARCHIVED),
            make_mission("MOONRAKER", 5, MissionStatus.ARCHIVED, minute=1),
            make_mission("OCTOPUSSY", 5, MissionStatus.ARCHIVED, minute=2),
        ]
        report = compute_risk(missions)
        self.assertEqual(report.total, 0)
        self.assertIs(report.level, RiskLevel.LOW)
        self.assertEqual(report.active_missions, ())

    def test_archived_missions_are_ignored(self) -> None:
        missions = [
            make_mission("SKYFALL", 4),
            make_mission("SPECTRE", 5, MissionStatus.ARCHIVED, minute=1),
            make_mission("GOLDENEYE", 3, minute=2),
        ]
        report = compute_risk(missions)
        self.assertEqual(report.total, 7)
        self.assertIs(report.level, RiskLevel.MEDIUM)
        self.assertEqual([m.code_name for m in report.active_missions], ["SKYFALL", "GOLDENEYE"])

    def test_archiving_can_lower_the_level(self) -> None:
        active = [make_mission("A", 5), make_mission("B", 5, minute=1), make_mission("C", 1, minute=2)]
        self.assertIs(compute_risk(active).level, RiskLevel.CRITICAL)
        active[2] = make_mission("C", 1, MissionStatus.ARCHIVED, minute=2)
        self.assertIs(compute_risk(active).level, RiskLevel.MEDIUM)


class ComputeRiskOrderTest(unittest.TestCase):
    def test_preserves_input_order(self) -> None:
        missions = [
            make_mission("ZULU", 1, minute=5),
            make_mission("ALPHA", 1, minute=1),
            make_mission("MIKE", 1, minute=3),
        ]
        report = compute_risk(missions)
        self.assertEqual([m.code_name for m in report.active_missions], ["ZULU", "ALPHA", "MIKE"])

    def test_same_minute_keeps_registration_order(self) -> None:
        missions = [make_mission("FIRST", 2), make_mission("SECOND", 2), make_mission("THIRD", 2)]
        report = compute_risk(missions)
        self.assertEqual(report.active_missions, tuple(missions))


class ComputeRiskPurityTest(unittest.TestCase):
    def test_does_not_mutate_input(self) -> None:
        missions = [
            make_mission("SKYFALL", 4),
            make_mission("SPECTRE", 5, MissionStatus.ARCHIVED, minute=1),
        ]
        snapshot = copy.deepcopy(missions)
        compute_risk(missions)
        self.assertEqual(missions, snapshot)

    def test_is_deterministic(self) -> None:
        missions = missions_with_total(13)
        self.assertEqual(compute_risk(missions), compute_risk(missions))

    def test_accepts_any_iterable(self) -> None:
        missions = missions_with_total(8)
        expected = compute_risk(missions)
        self.assertEqual(compute_risk(tuple(missions)), expected)
        self.assertEqual(compute_risk(m for m in missions), expected)

    def test_returns_immutable_report(self) -> None:
        report = compute_risk(missions_with_total(6))
        self.assertIsInstance(report, RiskReport)
        self.assertIsInstance(report.active_missions, tuple)

    def test_does_no_io(self) -> None:
        with mock.patch("builtins.open", side_effect=AssertionError("I/O in compute_risk")):
            compute_risk(missions_with_total(11))

    def test_module_has_no_io_or_clock_dependencies(self) -> None:
        for name in ("os", "sys", "time", "datetime", "pathlib", "random"):
            with self.subTest(module=name):
                self.assertNotIn(name, vars(risk))


if __name__ == "__main__":
    unittest.main()
