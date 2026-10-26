"""Global risk of an agent (RF-4.3, RF-4.4, RF-4.5, RF-5.3; plan, section 3)."""

from __future__ import annotations

from collections.abc import Iterable

from mi6.core.models import Mission, MissionStatus, RiskLevel, RiskReport

LOW_MAX = 5
MEDIUM_MAX = 10


def compute_risk(missions: Iterable[Mission]) -> RiskReport:
    """Sum the threat levels of the active missions and classify the total.

    Archived missions are ignored. Input order is preserved and the input is
    never mutated: 0..5 is LOW, 6..10 is MEDIUM and 11 or more is CRITICAL.
    """
    active = tuple(mission for mission in missions if mission.status == MissionStatus.ACTIVE)
    total = sum(mission.threat_level for mission in active)
    if total <= LOW_MAX:
        level = RiskLevel.LOW
    elif total <= MEDIUM_MAX:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.CRITICAL
    return RiskReport(active_missions=active, total=total, level=level)
