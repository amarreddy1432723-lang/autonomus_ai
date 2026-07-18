"""Mission scheduler for prioritized, resource-aware work selection."""

from __future__ import annotations

from dataclasses import dataclass

from .missions import OSMission


@dataclass(slots=True)
class SchedulerPolicy:
    max_concurrent_missions: int = 2
    allow_high_risk_without_approval: bool = False


class MissionScheduler:
    def __init__(self, policy: SchedulerPolicy | None = None) -> None:
        self.policy = policy or SchedulerPolicy()

    def select_ready(self, missions: list[OSMission], running_count: int = 0) -> list[OSMission]:
        capacity = max(0, self.policy.max_concurrent_missions - running_count)
        candidates = [
            mission
            for mission in missions
            if mission.state == "READY"
            and not mission.paused_by_user
            and not mission.dependencies
            and (self.policy.allow_high_risk_without_approval or mission.risk_level not in {"high", "critical"})
        ]
        return sorted(candidates, key=lambda mission: mission.priority_score, reverse=True)[:capacity]

