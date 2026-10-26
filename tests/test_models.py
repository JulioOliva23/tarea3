"""Tests for mi6.core.models (plan, sections 2.2 and 2.3; RF-3.4, RF-4.2, RF-5.2)."""

from __future__ import annotations

import dataclasses
import json
import unittest
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from mi6.core import models
from mi6.core.models import (
    AgentRecord,
    KdfParams,
    Mission,
    MissionsDocument,
    MissionStatus,
    RiskLevel,
    RiskReport,
)

BST = timezone(timedelta(hours=1))

# Example document from the plan, section 2.2.
PLAN_EXAMPLE = {
    "schema_version": 1,
    "agents": {
        "007": {
            "kdf": {
                "algorithm": "pbkdf2_hmac_sha256",
                "iterations": 600000,
                "salt": "q3Jx9mW2bT8vYp1LzK0aNg==",
            },
            "key_check": "gAAAAABnHf3k9vQ2...Xh8=",
            "missions": [
                {
                    "code_name": "SKYFALL",
                    "threat_level": 4,
                    "status": "active",
                    "created_at": "2026-10-20T09:15:42+01:00",
                    "report_token": "gAAAAABnFL1e2Rk7...pQ0=",
                },
                {
                    "code_name": "SPECTRE",
                    "threat_level": 5,
                    "status": "archived",
                    "created_at": "2026-10-22T23:04:10+01:00",
                    "report_token": "gAAAAABnGCk8Wf3Z...aM4=",
                },
                {
                    "code_name": "GOLDENEYE",
                    "threat_level": 3,
                    "status": "active",
                    "created_at": "2026-10-26T14:32:07+00:00",
                    "report_token": "gAAAAABnHf5j0LcY...tE2=",
                },
            ],
        },
        "006": {
            "kdf": {
                "algorithm": "pbkdf2_hmac_sha256",
                "iterations": 600000,
                "salt": "Zt4Hc1oPq8sWv0mN2xRyJA==",
            },
            "key_check": "gAAAAABnHa02Mz1T...Lw8=",
            "missions": [
                {
                    "code_name": "SKYFALL",
                    "threat_level": 2,
                    "status": "active",
                    "created_at": "2026-10-25T18:47:55+01:00",
                    "report_token": "gAAAAABnG9xQ7bNe...Vu1=",
                },
            ],
        },
    },
}


def skyfall() -> Mission:
    return Mission(
        code_name="SKYFALL",
        threat_level=4,
        status=MissionStatus.ACTIVE,
        created_at=datetime(2026, 10, 20, 9, 15, 42, tzinfo=BST),
        report_token="gAAAAABnFL1e2Rk7...pQ0=",
    )


def plan_example_document() -> MissionsDocument:
    agent_007 = AgentRecord(
        kdf=KdfParams(salt="q3Jx9mW2bT8vYp1LzK0aNg==", iterations=600000),
        key_check="gAAAAABnHf3k9vQ2...Xh8=",
        missions=[
            skyfall(),
            Mission(
                "SPECTRE", 5, MissionStatus.ARCHIVED,
                datetime(2026, 10, 22, 23, 4, 10, tzinfo=BST), "gAAAAABnGCk8Wf3Z...aM4=",
            ),
            Mission(
                "GOLDENEYE", 3, MissionStatus.ACTIVE,
                datetime(2026, 10, 26, 14, 32, 7, tzinfo=timezone.utc), "gAAAAABnHf5j0LcY...tE2=",
            ),
        ],
    )
    agent_006 = AgentRecord(
        kdf=KdfParams(salt="Zt4Hc1oPq8sWv0mN2xRyJA==", iterations=600000),
        key_check="gAAAAABnHa02Mz1T...Lw8=",
        missions=[
            Mission(
                "SKYFALL", 2, MissionStatus.ACTIVE,
                datetime(2026, 10, 25, 18, 47, 55, tzinfo=BST), "gAAAAABnG9xQ7bNe...Vu1=",
            ),
        ],
    )
    return MissionsDocument(agents={"007": agent_007, "006": agent_006})


class ConstantsTest(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(models.SCHEMA_VERSION, 1)
        self.assertEqual(models.KDF_ALGORITHM, "pbkdf2_hmac_sha256")


class StrEnumTest(unittest.TestCase):
    def test_mission_status_members(self) -> None:
        self.assertTrue(issubclass(MissionStatus, StrEnum))
        self.assertEqual({s.value for s in MissionStatus}, {"active", "archived"})
        self.assertEqual(MissionStatus.ACTIVE, "active")
        self.assertEqual(MissionStatus.ARCHIVED, "archived")

    def test_risk_level_members(self) -> None:
        self.assertTrue(issubclass(RiskLevel, StrEnum))
        self.assertEqual([level.value for level in RiskLevel], ["low", "medium", "critical"])

    def test_members_behave_as_plain_strings(self) -> None:
        for member in [*MissionStatus, *RiskLevel]:
            with self.subTest(member=member):
                self.assertIsInstance(member, str)
                self.assertEqual(str(member), member.value)
                self.assertEqual(f"{member}", member.value)
                self.assertEqual(json.dumps(member), json.dumps(member.value))

    def test_lookup_by_value(self) -> None:
        self.assertIs(MissionStatus("active"), MissionStatus.ACTIVE)
        self.assertIs(RiskLevel("critical"), RiskLevel.CRITICAL)
        with self.assertRaises(ValueError):
            MissionStatus("lost")
        with self.assertRaises(ValueError):
            RiskLevel("high")


class FrozenTest(unittest.TestCase):
    def instances(self) -> dict[str, object]:
        record = plan_example_document().agents["007"]
        return {
            "KdfParams": record.kdf,
            "Mission": skyfall(),
            "AgentRecord": record,
            "RiskReport": RiskReport(active_missions=(skyfall(),), total=4, level=RiskLevel.LOW),
            "MissionsDocument": plan_example_document(),
        }

    def test_all_models_are_frozen_dataclasses(self) -> None:
        for name, instance in self.instances().items():
            with self.subTest(model=name):
                self.assertTrue(dataclasses.is_dataclass(instance))
                self.assertTrue(type(instance).__dataclass_params__.frozen)

    def test_fields_cannot_be_reassigned(self) -> None:
        for name, instance in self.instances().items():
            for field in dataclasses.fields(instance):
                with self.subTest(model=name, field=field.name):
                    with self.assertRaises(dataclasses.FrozenInstanceError):
                        setattr(instance, field.name, None)

    def test_new_attributes_cannot_be_added(self) -> None:
        for name, instance in self.instances().items():
            with self.subTest(model=name):
                with self.assertRaises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                    instance.extra = 1  # type: ignore[attr-defined]

    def test_fields_cannot_be_deleted(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            del skyfall().code_name

    def test_replace_returns_new_instance(self) -> None:
        original = skyfall()
        archived = dataclasses.replace(original, status=MissionStatus.ARCHIVED)
        self.assertIs(original.status, MissionStatus.ACTIVE)
        self.assertIs(archived.status, MissionStatus.ARCHIVED)
        self.assertEqual(archived.report_token, original.report_token)


class DeepImmutabilityTest(unittest.TestCase):
    def test_agent_record_stores_missions_as_tuple(self) -> None:
        source = [skyfall()]
        record = AgentRecord(KdfParams("salt", 1), "check", source)
        source.append(skyfall())
        self.assertIsInstance(record.missions, tuple)
        self.assertEqual(len(record.missions), 1)

    def test_risk_report_stores_missions_as_tuple(self) -> None:
        source = [skyfall()]
        report = RiskReport(active_missions=source, total=4, level=RiskLevel.LOW)
        source.clear()
        self.assertEqual(report.active_missions, (skyfall(),))

    def test_document_agents_are_read_only_and_copied(self) -> None:
        source = {"007": plan_example_document().agents["007"]}
        document = MissionsDocument(agents=source)
        source["008"] = source["007"]
        self.assertEqual(list(document.agents), ["007"])
        with self.assertRaises(TypeError):
            document.agents["009"] = source["007"]  # type: ignore[index]
        with self.assertRaises(TypeError):
            del document.agents["007"]  # type: ignore[attr-defined]


class CoercionTest(unittest.TestCase):
    def test_mission_status_string_becomes_enum(self) -> None:
        mission = dataclasses.replace(skyfall(), status="archived")
        self.assertIs(mission.status, MissionStatus.ARCHIVED)

    def test_mission_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValueError):
            dataclasses.replace(skyfall(), status="lost")

    def test_risk_level_string_becomes_enum(self) -> None:
        report = RiskReport(active_missions=(), total=0, level="low")
        self.assertIs(report.level, RiskLevel.LOW)

    def test_risk_report_rejects_unknown_level(self) -> None:
        with self.assertRaises(ValueError):
            RiskReport(active_missions=(), total=0, level="high")


class ToDictTest(unittest.TestCase):
    def test_kdf_params(self) -> None:
        kdf = KdfParams(salt="q3Jx9mW2bT8vYp1LzK0aNg==", iterations=600000)
        self.assertEqual(kdf.algorithm, "pbkdf2_hmac_sha256")
        self.assertEqual(
            kdf.to_dict(),
            {"algorithm": "pbkdf2_hmac_sha256", "iterations": 600000, "salt": "q3Jx9mW2bT8vYp1LzK0aNg=="},
        )

    def test_mission(self) -> None:
        data = skyfall().to_dict()
        self.assertEqual(data, PLAN_EXAMPLE["agents"]["007"]["missions"][0])
        self.assertEqual(list(data), ["code_name", "threat_level", "status", "created_at", "report_token"])
        self.assertIs(type(data["status"]), str)
        self.assertIs(type(data["threat_level"]), int)

    def test_mission_created_at_keeps_offset_and_drops_microseconds(self) -> None:
        mission = dataclasses.replace(
            skyfall(), created_at=datetime(2026, 10, 26, 14, 32, 7, 999999, tzinfo=timezone.utc)
        )
        self.assertEqual(mission.to_dict()["created_at"], "2026-10-26T14:32:07+00:00")

    def test_created_at_round_trips_with_fromisoformat(self) -> None:
        mission = skyfall()
        parsed = datetime.fromisoformat(mission.to_dict()["created_at"])
        self.assertEqual(parsed, mission.created_at)
        self.assertEqual(parsed.utcoffset(), timedelta(hours=1))

    def test_agent_record(self) -> None:
        record = plan_example_document().agents["007"]
        self.assertEqual(record.to_dict(), PLAN_EXAMPLE["agents"]["007"])
        self.assertEqual(list(record.to_dict()), ["kdf", "key_check", "missions"])

    def test_risk_report(self) -> None:
        report = RiskReport(active_missions=(skyfall(),), total=4, level=RiskLevel.LOW)
        data = report.to_dict()
        self.assertEqual(
            data,
            {
                "active_missions": [PLAN_EXAMPLE["agents"]["007"]["missions"][0]],
                "total": 4,
                "level": "low",
            },
        )
        self.assertIs(type(data["level"]), str)

    def test_document_matches_plan_example(self) -> None:
        self.assertEqual(plan_example_document().to_dict(), PLAN_EXAMPLE)

    def test_document_preserves_agent_and_mission_order(self) -> None:
        data = plan_example_document().to_dict()
        self.assertEqual(list(data), ["schema_version", "agents"])
        self.assertEqual(list(data["agents"]), ["007", "006"])
        self.assertEqual(
            [m["code_name"] for m in data["agents"]["007"]["missions"]],
            ["SKYFALL", "SPECTRE", "GOLDENEYE"],
        )

    def test_document_is_json_serializable(self) -> None:
        text = json.dumps(plan_example_document().to_dict(), ensure_ascii=False, indent=2)
        self.assertEqual(json.loads(text), PLAN_EXAMPLE)

    def test_empty_document(self) -> None:
        document = MissionsDocument()
        self.assertEqual(document.schema_version, 1)
        self.assertEqual(document.to_dict(), {"schema_version": 1, "agents": {}})

    def test_to_dict_returns_independent_copies(self) -> None:
        document = plan_example_document()
        first = document.to_dict()
        first["agents"]["007"]["missions"].clear()
        self.assertEqual(document.to_dict(), PLAN_EXAMPLE)


class FindMissionTest(unittest.TestCase):
    def test_finds_by_exact_code_name(self) -> None:
        record = plan_example_document().agents["007"]
        mission = record.find_mission("SPECTRE")
        self.assertIsNotNone(mission)
        self.assertIs(mission.status, MissionStatus.ARCHIVED)

    def test_returns_none_when_missing(self) -> None:
        record = plan_example_document().agents["007"]
        self.assertIsNone(record.find_mission("MOONRAKER"))
        self.assertIsNone(record.find_mission("skyfall"))

    def test_same_code_name_in_two_agents_is_independent(self) -> None:
        document = plan_example_document()
        self.assertEqual(document.agents["007"].find_mission("SKYFALL").threat_level, 4)
        self.assertEqual(document.agents["006"].find_mission("SKYFALL").threat_level, 2)


if __name__ == "__main__":
    unittest.main()
