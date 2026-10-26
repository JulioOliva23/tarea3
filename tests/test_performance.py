"""RNF-6 performance budget with 1,000 stored missions (task T45; plan, section 6.4).

The fixture is a real, schema-valid missions.json: every agent has its own
salt and verifier and every report is a real Fernet token. Only PBKDF2 runs
with FAST_ITERATIONS so that building the fixture stays cheap; listing never
derives keys, so the measured path is identical to production.

Creating and archiving with the production 600,000 iterations is measured
manually, as the plan prescribes, and recorded in README.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from unittest import mock

from mi6.core import crypto, operations, storage
from mi6.core.models import AgentRecord, KdfParams, Mission, MissionsDocument, MissionStatus
from tests.test_base import FAST_ITERATIONS, IS_ROOT, MI6TestCase

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TOTAL_MISSIONS = 1_000
AGENT_UNDER_TEST = "007"
MISSIONS_FOR_AGENT = 400
LIST_BUDGET_SECONDS = 1.0


def build_document(now, total: int = TOTAL_MISSIONS) -> MissionsDocument:
    """Spread ``total`` missions over the nine agents; agent 007 gets MISSIONS_FOR_AGENT.

    Every fourth mission of each agent is archived, so filtering is exercised.
    """
    others = [f"00{number}" for number in range(1, 10) if f"00{number}" != AGENT_UNDER_TEST]
    per_other, remainder = divmod(total - MISSIONS_FOR_AGENT, len(others))
    counts = {AGENT_UNDER_TEST: MISSIONS_FOR_AGENT}
    for index, code in enumerate(others):
        counts[code] = per_other + (1 if index < remainder else 0)

    agents = {}
    sequence = 0
    for code, count in counts.items():
        salt = crypto.new_salt()
        key = crypto.derive_key(f"clave-{code}-segura", salt, FAST_ITERATIONS)
        missions = []
        for index in range(count):
            missions.append(
                Mission(
                    code_name=f"OP-{code}-{index:04d}",
                    threat_level=index % 5 + 1,
                    status=MissionStatus.ARCHIVED if index % 4 == 3 else MissionStatus.ACTIVE,
                    created_at=now + timedelta(seconds=sequence),
                    report_token=crypto.encrypt_report(key, f"Informe {index} del agente {code}."),
                )
            )
            sequence += 1
        agents[code] = AgentRecord(
            kdf=KdfParams(salt=crypto.encode_salt(salt), iterations=FAST_ITERATIONS),
            key_check=crypto.make_key_check(key),
            missions=missions,
        )
    return MissionsDocument(agents=agents)


class PerformanceTestCase(MI6TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.document = build_document(self.now)
        storage.initialize_data_dir(self.data_dir)
        storage.write_document_atomic(self.data_dir, self.document.to_dict())
        self.expected_active = [
            mission.code_name
            for mission in self.document.agents[AGENT_UNDER_TEST].missions
            if mission.status is MissionStatus.ACTIVE
        ]


class FixtureTest(PerformanceTestCase):
    def test_fixture_has_1000_valid_missions(self) -> None:
        total = sum(len(record.missions) for record in self.document.agents.values())
        self.assertEqual(total, TOTAL_MISSIONS)
        self.assertEqual(len(self.document.agents), 9)
        self.assertEqual(len(self.expected_active), 300)
        reloaded = operations._load_document(self.data_dir)
        self.assertEqual(reloaded, self.document)


class ListPerformanceTest(PerformanceTestCase):
    def test_list_active_missions_under_one_second(self) -> None:
        start = time.perf_counter()
        report = operations.list_active_missions(self.data_dir, AGENT_UNDER_TEST)
        elapsed = time.perf_counter() - start
        self.assertEqual([mission.code_name for mission in report.active_missions], self.expected_active)
        self.assertEqual(report.total, sum(i % 5 + 1 for i in range(MISSIONS_FOR_AGENT) if i % 4 != 3))
        self.assertLess(elapsed, LIST_BUDGET_SECONDS, f"list took {elapsed:.3f}s with {TOTAL_MISSIONS} missions")

    def test_list_stays_under_budget_on_repeated_runs(self) -> None:
        timings = []
        for _ in range(5):
            start = time.perf_counter()
            operations.list_active_missions(self.data_dir, AGENT_UNDER_TEST)
            timings.append(time.perf_counter() - start)
        self.assertLess(max(timings), LIST_BUDGET_SECONDS, f"timings: {timings}")

    def test_list_never_derives_keys(self) -> None:
        with mock.patch.object(crypto, "derive_key", wraps=crypto.derive_key) as derive_key:
            operations.list_active_missions(self.data_dir, AGENT_UNDER_TEST)
        derive_key.assert_not_called()


class CommandPerformanceTest(PerformanceTestCase):
    """RNF-6 measures from the moment the command is launched, so a real process is used."""

    def run_command(self, *argv: str) -> tuple[subprocess.CompletedProcess[str], float]:
        env = {
            **os.environ,
            "HOME": str(self.home),
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONIOENCODING": "utf-8",
        }
        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-m", "mi6", *argv],
            cwd=self.tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return completed, time.perf_counter() - start

    def test_python_m_mi6_list_under_one_second(self) -> None:
        if IS_ROOT:
            self.skipTest("mi6 refuses to run as root")
        completed, elapsed = self.run_command("list", "-a", AGENT_UNDER_TEST)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        lines = completed.stdout.splitlines()
        self.assertEqual(lines[0], "MISIONES ACTIVAS · AGENTE 007")
        self.assertEqual(len(lines), 2 + len(self.expected_active) + 2)
        self.assertTrue(lines[-1].startswith("RIESGO GLOBAL: "))
        self.assertTrue(lines[-1].endswith("· CRÍTICO"))
        self.assertLess(elapsed, LIST_BUDGET_SECONDS, f"'python -m mi6 list' took {elapsed:.3f}s")

    def test_command_uses_sandboxed_home_only(self) -> None:
        if IS_ROOT:
            self.skipTest("mi6 refuses to run as root")
        before = self.snapshot_dir()
        completed, _ = self.run_command("list", "-a", "001")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.snapshot_dir(), before)
