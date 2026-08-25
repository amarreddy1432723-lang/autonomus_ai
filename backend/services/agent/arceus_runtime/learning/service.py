from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import ArceusEvidence, ArceusLessonProposal, ArceusParticipant, ArceusPerformanceObservation


TRUSTED_EVIDENCE_STATUSES = {"validated", "trusted", "verified"}
TRUSTED_EVIDENCE_LEVELS = {"tool_verified", "independent_review", "human_approved", "production_observed"}
PROMOTION_THRESHOLDS = {
    "mission": 1,
    "project": 2,
    "organization": 3,
    "global": 5,
}

SKILL_METRIC_PREFIX = "skill."
MODEL_ATTRIBUTION_KEYS = ("model_key", "model", "selected_model_key")
TASK_ATTRIBUTION_KEYS = ("task_type", "capability", "mission_type")
KNOWLEDGE_VALIDATION_LEVELS = (
    (101, "organization_standard"),
    (26, "validated"),
    (5, "candidate"),
    (0, "temporary"),
)


def trusted_evidence(evidence: list[ArceusEvidence]) -> list[ArceusEvidence]:
    return [
        item
        for item in evidence
        if item.status in TRUSTED_EVIDENCE_STATUSES or item.trust_level in TRUSTED_EVIDENCE_LEVELS
    ]


def evaluate_learning_record(*, evidence: list[ArceusEvidence], evidence_ids: list[UUID]) -> dict[str, Any]:
    trusted = trusted_evidence(evidence)
    missing_count = max(0, len(evidence_ids) - len(evidence))
    if missing_count:
        return {
            "status": "blocked_missing_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": len(trusted),
            "reason": "Learning record references evidence that does not exist in this tenant or mission.",
        }
    if not evidence_ids:
        return {
            "status": "blocked_no_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": 0,
            "reason": "Learning records require verified evidence before they can influence future work.",
        }
    if not trusted:
        return {
            "status": "blocked_unverified_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": 0,
            "reason": "Evidence exists but is not trusted, validated, verified, or independently reviewed.",
        }
    return {
        "status": "proposed",
        "promotion_ready": True,
        "trusted_evidence_count": len(trusted),
        "reason": "Verified evidence is present; learning can enter governed review.",
    }


def pattern_key_for_lesson(lesson: ArceusLessonProposal) -> str:
    text = f"{lesson.title} {lesson.lesson}".lower()
    if any(word in text for word in ["test", "verification", "qa", "build"]):
        return "quality.verification"
    if any(word in text for word in ["security", "auth", "permission", "secret"]):
        return "security.governance"
    if any(word in text for word in ["plan", "scope", "requirement", "roadmap"]):
        return "planning.scope_control"
    if any(word in text for word in ["latency", "performance", "cache", "cost"]):
        return "operations.optimization"
    return "engineering.practice"


def discover_patterns(lessons: list[ArceusLessonProposal]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ArceusLessonProposal]] = defaultdict(list)
    for lesson in lessons:
        grouped[pattern_key_for_lesson(lesson)].append(lesson)

    rows: list[dict[str, Any]] = []
    for key, items in grouped.items():
        support_count = len(items)
        evidence_ids = []
        approved_count = 0
        for item in items:
            evidence_ids.extend([UUID(str(evidence_id)) for evidence_id in item.evidence_ids])
            if item.status == "approved":
                approved_count += 1
        confidence = min(0.98, 0.35 + support_count * 0.15 + approved_count * 0.15)
        promotion_level = "candidate"
        if support_count >= PROMOTION_THRESHOLDS["organization"] and approved_count:
            promotion_level = "organization_candidate"
        elif support_count >= PROMOTION_THRESHOLDS["project"]:
            promotion_level = "project_candidate"
        rows.append(
            {
                "pattern_key": key,
                "title": key.replace(".", " ").title(),
                "category": key.split(".", 1)[0],
                "confidence": round(confidence, 3),
                "support_count": support_count,
                "promotion_level": promotion_level,
                "evidence_ids": sorted(set(evidence_ids), key=str),
                "status": "review_required" if confidence >= 0.65 else "collecting_evidence",
            }
        )
    return sorted(rows, key=lambda item: (-item["confidence"], item["pattern_key"]))


def validation_level_for_support(support_count: int) -> str:
    for threshold, level in KNOWLEDGE_VALIDATION_LEVELS:
        if support_count >= threshold:
            return level
    return "temporary"


def build_organization_brain(
    *,
    missions: list[Any],
    lessons: list[ArceusLessonProposal],
    evidence: list[ArceusEvidence],
    observations: list[ArceusPerformanceObservation],
    participants: list[ArceusParticipant],
    project_id: UUID | None = None,
    repository_id: UUID | None = None,
) -> dict[str, Any]:
    """Compose the Organization Brain from governed runtime records.

    This is intentionally a read model over existing durable mission, evidence,
    learning, and participant tables. It keeps the first Organization Brain
    slice useful without introducing parallel persistence that can drift.
    """
    scoped_missions = [mission for mission in missions if project_id is None or mission.project_id == project_id]
    scoped_mission_ids = {mission.id for mission in scoped_missions}
    scoped_lessons = [lesson for lesson in lessons if lesson.mission_id in scoped_mission_ids]
    scoped_evidence = [item for item in evidence if item.mission_id in scoped_mission_ids]
    scoped_observations = [item for item in observations if not item.mission_id or item.mission_id in scoped_mission_ids]

    patterns = discover_patterns(scoped_lessons)
    trusted_ids = {str(item.id) for item in trusted_evidence(scoped_evidence)}
    knowledge_candidates: list[dict[str, Any]] = []
    for pattern in patterns:
        evidence_ids = [str(item) for item in pattern["evidence_ids"]]
        trusted_count = len([item for item in evidence_ids if item in trusted_ids])
        approved_count = len([lesson for lesson in scoped_lessons if pattern_key_for_lesson(lesson) == pattern["pattern_key"] and lesson.status == "approved"])
        success_rate = round(min(0.99, 0.58 + trusted_count * 0.012 + approved_count * 0.03), 3)
        validation_level = validation_level_for_support(pattern["support_count"])
        knowledge_candidates.append(
            {
                **pattern,
                "trusted_evidence_count": trusted_count,
                "success_rate": success_rate,
                "validation_level": validation_level,
                "recommendation": "promote_to_standard" if validation_level == "organization_standard" and approved_count else (
                    "validated_knowledge" if validation_level == "validated" else (
                        "collect_more_evidence" if validation_level == "temporary" else "review_for_project_reuse"
                    )
                ),
            }
        )

    standards = [
        {
            "standard_key": item["pattern_key"],
            "title": item["title"],
            "category": item["category"],
            "confidence": item["confidence"],
            "support_count": item["support_count"],
            "trusted_evidence_count": item["trusted_evidence_count"],
            "status": "active" if item["validation_level"] == "organization_standard" else "validated",
            "rule": f"Apply {item['title']} when mission context matches {item['category']} work.",
        }
        for item in knowledge_candidates
        if item["validation_level"] in {"validated", "organization_standard"}
    ]

    skill_matrix = build_agent_skill_matrix(participants=participants, observations=scoped_observations)
    recurring_failures = [
        {
            "metric": item.metric_key,
            "mission_id": item.mission_id,
            "value": round(float(item.metric_value), 4),
        }
        for item in scoped_observations
        if float(item.metric_value) < 0.7 and item.metric_key not in {"agent.task_failed"}
    ][:20]
    completed_missions = [mission for mission in scoped_missions if mission.status in {"completed", "verified", "closed"} or mission.completed_at]
    failed_missions = [mission for mission in scoped_missions if mission.status in {"failed", "cancelled"} or mission.failed_at]
    mission_success_rate = round(len(completed_missions) / len(scoped_missions), 4) if scoped_missions else 0.0
    repository_memory = {
        "project_id": project_id,
        "repository_id": repository_id,
        "mission_count": len(scoped_missions),
        "previous_missions": len(scoped_missions),
        "known_risks": sorted({item["category"] for item in knowledge_candidates if item["category"] in {"security", "quality", "operations", "planning"}}),
        "validated_patterns": [item["title"] for item in knowledge_candidates if item["validation_level"] in {"validated", "organization_standard"}],
        "preferred_agents": [item["name"] for item in skill_matrix[:3]],
        "recommended_next_mission": _recommended_next_mission(knowledge_candidates, recurring_failures),
    }
    graph_nodes = [
        {"id": f"pattern:{item['pattern_key']}", "type": "knowledge_candidate", "label": item["title"], "confidence": item["confidence"]}
        for item in knowledge_candidates[:25]
    ]
    graph_nodes.extend(
        {"id": f"agent:{item['agent_id']}", "type": "agent", "label": item["name"], "confidence": round(item["overall_score"] / 100, 3)}
        for item in skill_matrix[:25]
    )
    graph_edges = [
        {"from": f"pattern:{item['pattern_key']}", "to": f"category:{item['category']}", "relation": "belongs_to", "confidence": item["confidence"]}
        for item in knowledge_candidates[:25]
    ]
    ceo_recommendations = _ceo_recommendations(
        knowledge_candidates=knowledge_candidates,
        standards=standards,
        skill_matrix=skill_matrix,
        recurring_failures=recurring_failures,
        mission_success_rate=mission_success_rate,
    )
    return {
        "brain_status": "learning" if scoped_missions else "empty",
        "project_id": project_id,
        "repository_id": repository_id,
        "mission_count": len(scoped_missions),
        "trusted_evidence_count": len(trusted_evidence(scoped_evidence)),
        "mission_success_rate": mission_success_rate,
        "knowledge_candidates": knowledge_candidates,
        "engineering_standards": standards,
        "repository_memory": repository_memory,
        "agent_skill_profiles": skill_matrix,
        "dynamic_scheduling": {
            "strategy": "rank_required_capabilities_against_skill_profiles",
            "top_agents": skill_matrix[:5],
            "rule": "Never assign solely by fixed role when learned capability evidence is available.",
        },
        "cross_agent_review": {
            "required_for": ["organization_standard", "security", "architecture", "production"],
            "reviewers": ["architecture", "qa", "security"],
            "rule": "Knowledge cannot become permanent until evidence and independent review agree.",
        },
        "knowledge_graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
        },
        "ceo_agent": {
            "responsibilities": ["monitor_organization", "approve_standards", "detect_bottlenecks", "recommend_training", "promote_best_practices"],
            "recommendations": ceo_recommendations,
        },
    }


def _recommended_next_mission(knowledge_candidates: list[dict[str, Any]], recurring_failures: list[dict[str, Any]]) -> str:
    if recurring_failures:
        metric = recurring_failures[0]["metric"].replace("_", " ")
        return f"Investigate repeated weakness in {metric}."
    if knowledge_candidates:
        top = knowledge_candidates[0]
        if top["validation_level"] == "temporary":
            return f"Collect more evidence for {top['title']}."
        return f"Apply validated pattern: {top['title']}."
    return "Open a repository and complete the first evidence-backed mission."


def _ceo_recommendations(
    *,
    knowledge_candidates: list[dict[str, Any]],
    standards: list[dict[str, Any]],
    skill_matrix: list[dict[str, Any]],
    recurring_failures: list[dict[str, Any]],
    mission_success_rate: float,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if recurring_failures:
        recommendations.append(
            {
                "type": "bottleneck",
                "title": "Investigate recurring low-scoring execution signals",
                "confidence": 0.86,
                "reason": f"{len(recurring_failures)} weak metric signal(s) were found in recent mission observations.",
            }
        )
    promotable = [item for item in knowledge_candidates if item["validation_level"] in {"validated", "organization_standard"} and item["recommendation"] != "collect_more_evidence"]
    if promotable and not standards:
        recommendations.append(
            {
                "type": "standardization",
                "title": "Review validated patterns for engineering standards",
                "confidence": promotable[0]["confidence"],
                "reason": f"{promotable[0]['title']} has enough evidence for stronger reuse.",
            }
        )
    weak_agents = [item for item in skill_matrix if item["weak_areas"]]
    if weak_agents:
        recommendations.append(
            {
                "type": "training",
                "title": f"Train {weak_agents[0]['name']} on {weak_agents[0]['weak_areas'][0]}",
                "confidence": 0.78,
                "reason": "Skill profile shows a capability gap that can affect future scheduling.",
            }
        )
    if mission_success_rate and mission_success_rate < 0.8:
        recommendations.append(
            {
                "type": "reliability",
                "title": "Pause broad automation and improve mission reliability",
                "confidence": 0.9,
                "reason": f"Mission success rate is {round(mission_success_rate * 100, 1)}%.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "type": "next_mission",
                "title": "Run another evidence-backed repository mission",
                "confidence": 0.74,
                "reason": "More verified missions will strengthen repository memory and organizational standards.",
            }
        )
    return recommendations


def scorecard_from_observations(*, subject_type: str, subject_id: UUID | None, observations: list[ArceusPerformanceObservation]) -> dict[str, Any]:
    metrics: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        if observation.subject_type == subject_type and (subject_id is None or observation.subject_id == subject_id):
            metrics[observation.metric_key].append(float(observation.metric_value))
    averaged = {key: round(sum(values) / len(values), 4) for key, values in metrics.items() if values}
    return scorecard_from_metrics(subject_type=subject_type, subject_id=subject_id, metrics=averaged)


def scorecard_from_metrics(*, subject_type: str, subject_id: UUID | None, metrics: dict[str, float]) -> dict[str, Any]:
    normalized: dict[str, float] = {}
    for key, value in metrics.items():
        normalized[key] = max(0.0, min(1.0, float(value)))
    score = round((sum(normalized.values()) / len(normalized)) * 100, 2) if normalized else 0.0
    strengths = [key for key, value in normalized.items() if value >= 0.85]
    improvement_areas = [key for key, value in normalized.items() if value < 0.7]
    if score >= 85:
        status = "strong"
    elif score >= 70:
        status = "stable"
    elif score > 0:
        status = "needs_improvement"
    else:
        status = "insufficient_data"
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "score": score,
        "status": status,
        "metrics": normalized,
        "strengths": strengths,
        "improvement_areas": improvement_areas,
    }


def synthesize_mission_reflection(
    *,
    mission_id: UUID,
    lessons: list[ArceusLessonProposal],
    evidence: list[ArceusEvidence],
    observations: list[ArceusPerformanceObservation],
) -> dict[str, Any]:
    """Build the after-action learning packet every completed mission should produce."""
    trusted = trusted_evidence(evidence)
    proposed_lessons = [item for item in lessons if item.mission_id == mission_id]
    trusted_evidence_ids = {str(item.id) for item in trusted}
    reusable_lessons = [
        {
            "learning_id": item.id,
            "title": item.title,
            "lesson": item.lesson,
            "impact": item.impact,
            "status": item.status,
            "trusted_evidence_count": len([evidence_id for evidence_id in item.evidence_ids if str(evidence_id) in trusted_evidence_ids]),
        }
        for item in proposed_lessons
        if item.status in {"proposed", "approved"}
    ]
    mission_metrics: dict[str, list[float]] = defaultdict(list)
    weak_metrics: list[str] = []
    strong_metrics: list[str] = []
    for observation in observations:
        if observation.mission_id != mission_id:
            continue
        value = max(0.0, min(1.0, float(observation.metric_value)))
        mission_metrics[observation.metric_key].append(value)
    averaged = {key: sum(values) / len(values) for key, values in mission_metrics.items() if values}
    for key, value in averaged.items():
        if value >= 0.85:
            strong_metrics.append(key)
        elif value < 0.7:
            weak_metrics.append(key)
    patterns = discover_patterns(proposed_lessons)
    promotion_candidates = [
        pattern
        for pattern in patterns
        if pattern["status"] == "review_required" and pattern["support_count"] >= PROMOTION_THRESHOLDS["project"]
    ]
    return {
        "mission_id": mission_id,
        "reflection_status": "ready_for_review" if trusted else "blocked_until_evidence",
        "what_worked": strong_metrics or ["No high-confidence strengths recorded yet."],
        "what_failed": weak_metrics or ["No low-scoring failure signal recorded."],
        "inefficiencies": [key for key in weak_metrics if any(word in key for word in ["latency", "cost", "speed", "retry"])],
        "reusable_lessons": reusable_lessons,
        "promotion_candidates": promotion_candidates,
        "organization_memory_updates": [
            {
                "scope": "organization",
                "title": item["title"],
                "confidence": min(0.98, 0.5 + item["trusted_evidence_count"] * 0.16),
                "requires_review": item["status"] != "approved",
            }
            for item in reusable_lessons
            if item["trusted_evidence_count"] > 0
        ],
        "training_priorities": [f"Improve {metric}" for metric in weak_metrics],
        "future_context": [
            "Load approved lessons matching the mission capability before planning.",
            "Use proposed lessons only as review hints until promoted.",
            "Do not let unverified lessons become organization standards.",
        ],
        "trusted_evidence_count": len(trusted),
    }


def _capability_key(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def _participant_capability_scores(participant: ArceusParticipant) -> dict[str, float]:
    scores: dict[str, float] = {}
    for item in participant.capabilities or []:
        if isinstance(item, dict):
            key = str(item.get("capability_key") or item.get("key") or item.get("id") or "").strip()
            confidence = float(item.get("confidence", 0.75) or 0.75)
        else:
            key = str(item).strip()
            confidence = 0.75
        if key:
            scores[_capability_key(key)] = max(0.0, min(1.0, confidence))
    return scores


def build_agent_skill_matrix(
    *,
    participants: list[ArceusParticipant],
    observations: list[ArceusPerformanceObservation],
) -> list[dict[str, Any]]:
    """Turn durable observations into agent skill profiles without changing model weights."""
    observation_buckets: dict[UUID, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    completed: dict[UUID, int] = defaultdict(int)
    failed: dict[UUID, int] = defaultdict(int)
    for observation in observations:
        subject_id = observation.participant_id or observation.subject_id
        if not subject_id:
            continue
        value = max(0.0, min(1.0, float(observation.metric_value)))
        if observation.metric_key.startswith(SKILL_METRIC_PREFIX):
            observation_buckets[subject_id][_capability_key(observation.metric_key.removeprefix(SKILL_METRIC_PREFIX))].append(value)
        elif observation.metric_key in {"agent.task_success", "agent.review_score", "agent.rollback_safety", "agent.verification_quality"}:
            observation_buckets[subject_id][observation.metric_key].append(value)
        elif observation.metric_key == "agent.task_completed":
            completed[subject_id] += int(max(0, observation.metric_value))
        elif observation.metric_key == "agent.task_failed":
            failed[subject_id] += int(max(0, observation.metric_value))

    rows: list[dict[str, Any]] = []
    for participant in participants:
        skills = _participant_capability_scores(participant)
        for key, values in observation_buckets.get(participant.id, {}).items():
            skills[key] = round(sum(values) / len(values), 4)
        task_success = skills.get("agent.task_success", 0.75)
        review_score = skills.get("agent.review_score", 0.75)
        verification_quality = skills.get("agent.verification_quality", 0.75)
        capability_only = {key: value for key, value in skills.items() if not key.startswith("agent.")}
        capability_strength = sum(capability_only.values()) / len(capability_only) if capability_only else 0.75
        overall = round((task_success * 0.36 + review_score * 0.24 + verification_quality * 0.2 + capability_strength * 0.2) * 100, 2)
        rows.append(
            {
                "agent_id": participant.id,
                "name": participant.display_name,
                "role": participant.role_key,
                "status": participant.status,
                "completed_tasks": completed.get(participant.id, 0),
                "failed_tasks": failed.get(participant.id, 0),
                "overall_score": overall,
                "skills": dict(sorted(capability_only.items())),
                "strengths": sorted([key for key, value in capability_only.items() if value >= 0.85]),
                "weak_areas": sorted([key for key, value in capability_only.items() if value < 0.7]),
            }
        )
    return sorted(rows, key=lambda item: (-item["overall_score"], item["name"]))


def rank_agents_for_capabilities(
    *,
    required_capabilities: list[str],
    skill_matrix: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    required = [_capability_key(item) for item in required_capabilities if item.strip()]
    rows: list[dict[str, Any]] = []
    for agent in skill_matrix:
        skills = dict(agent.get("skills") or {})
        matched = [key for key in required if skills.get(key, 0) >= 0.7]
        missing = [key for key in required if key not in matched]
        capability_score = 1.0 if not required else sum(float(skills.get(key, 0)) for key in required) / len(required)
        availability = 1.0 if agent.get("status") in {"available", "waiting"} else 0.62
        score = round(max(0.0, min(1.0, capability_score * 0.76 + (float(agent.get("overall_score", 0)) / 100) * 0.16 + availability * 0.08)), 4)
        rows.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "role": agent["role"],
                "score": score,
                "matched_capabilities": matched,
                "missing_capabilities": missing,
                "reasons": [
                    f"overall score {agent['overall_score']}",
                    "matches " + ", ".join(matched) if matched else "no direct capability match",
                    f"status {agent['status']}",
                ],
            }
        )
    return sorted(rows, key=lambda item: (-item["score"], item["name"]))[:limit]


def model_performance_matrix(observations: list[ArceusPerformanceObservation]) -> list[dict[str, Any]]:
    """Track which model/provider performs best per task type from evidence-backed outcomes."""
    buckets: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    evidence: dict[tuple[str, str], set[str]] = defaultdict(set)
    for observation in observations:
        model_key = ""
        for key in MODEL_ATTRIBUTION_KEYS:
            model_key = str((observation.attribution or {}).get(key) or "")
            if model_key:
                break
        if not model_key:
            continue
        task_type = "general"
        for key in TASK_ATTRIBUTION_KEYS:
            task_type = str((observation.attribution or {}).get(key) or task_type)
            if task_type != "general":
                break
        metric_key = observation.metric_key
        if metric_key.startswith("model."):
            metric_key = metric_key.removeprefix("model.")
        buckets[(task_type, model_key)][metric_key].append(max(0.0, min(1.0, float(observation.metric_value))))
        for evidence_id in observation.evidence_ids or []:
            evidence[(task_type, model_key)].add(str(evidence_id))

    rows: list[dict[str, Any]] = []
    for (task_type, model_key), metrics in buckets.items():
        averaged = {key: round(sum(values) / len(values), 4) for key, values in metrics.items() if values}
        quality = averaged.get("quality", averaged.get("success", 0.75))
        cost = averaged.get("cost_efficiency", 0.75)
        latency = averaged.get("latency", 0.75)
        reliability = averaged.get("reliability", 0.75)
        score = round((quality * 0.42 + reliability * 0.28 + cost * 0.16 + latency * 0.14) * 100, 2)
        rows.append(
            {
                "task_type": task_type,
                "model_key": model_key,
                "score": score,
                "metrics": averaged,
                "evidence_count": len(evidence[(task_type, model_key)]),
                "routing_hint": "preferred" if score >= 85 else ("fallback" if score >= 72 else "review_before_use"),
            }
        )
    return sorted(rows, key=lambda item: (item["task_type"], -item["score"], item["model_key"]))


def evaluate_promotion(*, lesson: ArceusLessonProposal, evidence: list[ArceusEvidence], target_scope: str, dry_run: bool) -> dict[str, Any]:
    trusted_count = len(trusted_evidence(evidence))
    required = PROMOTION_THRESHOLDS[target_scope]
    approvals = ["mission_lead", "human_reviewer"]
    if target_scope in {"organization", "global"}:
        approvals.extend(["organization_owner", "security_reviewer"])
    if trusted_count < required:
        return {
            "accepted": False,
            "status": "blocked",
            "reason": f"{target_scope} promotion requires at least {required} trusted evidence item(s).",
            "required_approvals": approvals,
            "reversible": True,
        }
    if target_scope in {"organization", "global"} and lesson.status != "approved":
        return {
            "accepted": False,
            "status": "review_required",
            "reason": "Organization/global learning requires approved lesson status before promotion.",
            "required_approvals": approvals,
            "reversible": True,
        }
    return {
        "accepted": bool(dry_run or target_scope == "mission"),
        "status": "dry_run_accepted" if dry_run else ("approved" if target_scope == "mission" else "review_required"),
        "reason": "Promotion is evidence-backed and remains reversible/auditable.",
        "required_approvals": approvals,
        "reversible": True,
    }
