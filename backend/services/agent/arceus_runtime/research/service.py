from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from ..compiler.utils import stable_hash


DOMAINS = {
    "software_engineering",
    "artificial_intelligence",
    "cybersecurity",
    "product_innovation",
    "business_strategy",
    "healthcare",
    "finance",
    "education",
    "manufacturing",
    "robotics",
    "scientific_computing",
    "operations_research",
}

RESEARCH_ORGANIZATION = [
    {"role": "Chief Research Scientist", "responsibility": "Own scientific rigor, uncertainty, and research direction."},
    {"role": "Research Planner", "responsibility": "Translate observations into research goals and milestones."},
    {"role": "Literature Analyst", "responsibility": "Collect external and internal evidence with provenance."},
    {"role": "Experiment Designer", "responsibility": "Design reproducible experiments and simulations."},
    {"role": "Statistician", "responsibility": "Select analysis methods and quantify confidence."},
    {"role": "Verification Scientist", "responsibility": "Validate evidence and reproducibility."},
    {"role": "Innovation Reviewer", "responsibility": "Score novelty, value, merit, and implementation fit."},
    {"role": "Knowledge Curator", "responsibility": "Promote validated findings into governed memory."},
]


def normalize_domain(domain: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (domain or "").lower()).strip("_")
    return normalized if normalized in DOMAINS else "software_engineering"


def tokens(text: str) -> list[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z0-9_./:-]+", text or "") if len(item) > 2]


def infer_questions(objective: str, observations: list[str], metrics: list[str] | None = None) -> list[str]:
    text = " ".join([objective, *observations]).lower()
    questions = []
    if "fail" in text or "outage" in text or "incident" in text:
        questions.append("What conditions most reliably predict or prevent this failure?")
    if "time" in text or "speed" in text or "latency" in text:
        questions.append("Which intervention improves time-to-outcome without reducing quality?")
    if "cost" in text or "budget" in text:
        questions.append("Which approach improves outcome per unit cost?")
    if "security" in text or "risk" in text:
        questions.append("Which controls reduce risk while preserving usability?")
    for metric in metrics or []:
        questions.append(f"How should {metric} change for the research to be considered successful?")
    if not questions:
        questions.append("Which intervention produces the strongest measurable improvement?")
    return questions[:8]


def generate_hypotheses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observation = payload.get("observation") or "An opportunity for improvement was observed."
    goal = payload.get("research_goal") or payload.get("objective") or "Improve the target outcome."
    domain = normalize_domain(payload.get("domain", "software_engineering"))
    constraints = payload.get("constraints") or []
    count = int(payload.get("competing_count", 3))
    base = [
        ("intervention", f"If Arceus introduces a targeted automation for {goal}, then the observed problem will improve measurably."),
        ("process", f"If the workflow is redesigned around explicit checkpoints, then {goal} will improve with lower operational variance."),
        ("simulation", f"If rollout scenarios are simulated before execution, then risky edge cases will be detected before production."),
        ("knowledge", f"If verified organizational memory is recalled during planning, then repeated failure modes related to {observation} will decrease."),
        ("governance", f"If approval and evidence gates are adjusted to risk level, then {goal} will improve without increasing unsafe actions."),
    ]
    hypotheses = []
    for index, (kind, statement) in enumerate(base[:count], start=1):
        hypothesis_key = f"H{index}"
        novelty = 0.55 + (index * 0.05)
        feasibility = 0.84 - (index * 0.04)
        testability = 0.72 if kind in {"intervention", "process", "simulation"} else 0.64
        if domain in {"cybersecurity", "healthcare", "finance"}:
            feasibility -= 0.05
            testability -= 0.03
        hypotheses.append(
            {
                "hypothesis_key": hypothesis_key,
                "type": kind,
                "statement": statement,
                "rationale": f"Generated from observation and goal with constraints: {constraints or ['none']}.",
                "expected_effect": "measurable outcome improvement",
                "testability": round(max(0.1, min(0.98, testability)), 3),
                "novelty": round(max(0.1, min(0.98, novelty)), 3),
                "feasibility": round(max(0.1, min(0.98, feasibility)), 3),
                "primary_metric": infer_primary_metric(goal, observation),
            }
        )
    return hypotheses


def infer_primary_metric(goal: str, observation: str) -> str:
    text = f"{goal} {observation}".lower()
    if "fail" in text or "outage" in text:
        return "failure_rate"
    if "time" in text or "speed" in text:
        return "time_to_completion"
    if "cost" in text:
        return "cost_per_success"
    if "security" in text or "risk" in text:
        return "risk_reduction"
    return "success_rate"


def uncertainty_model(hypotheses: list[dict[str, Any]], evidence_ids: list[str] | None = None) -> dict[str, Any]:
    evidence_count = len(evidence_ids or [])
    known = ["research_goal_defined"] if hypotheses else []
    probable = [item["statement"] for item in hypotheses if item["feasibility"] >= 0.7]
    uncertain = []
    if evidence_count == 0:
        uncertain.append("No external or verified evidence has been attached yet.")
    if any(item["testability"] < 0.7 for item in hypotheses):
        uncertain.append("Some hypotheses need clearer metrics or experiment design.")
    unknown = ["actual_effect_size", "environment_specific_constraints"]
    confidence = round(min(0.9, 0.42 + evidence_count * 0.08 + mean([item["testability"] for item in hypotheses] or [0.5]) * 0.24), 3)
    return {"known_facts": known, "probable_findings": probable[:5], "uncertain_areas": uncertain, "unknown_questions": unknown, "confidence": confidence}


def build_research_project(payload: dict[str, Any]) -> dict[str, Any]:
    domain = normalize_domain(payload.get("domain", "software_engineering"))
    questions = payload.get("research_questions") or infer_questions(payload["objective"], payload.get("observations") or [], payload.get("success_metrics") or [])
    hypotheses = generate_hypotheses(
        {
            "observation": " ".join(payload.get("observations") or [payload["objective"]]),
            "research_goal": payload["objective"],
            "domain": domain,
            "constraints": payload.get("constraints") or [],
            "competing_count": 3,
        }
    )
    uncertainty = uncertainty_model(hypotheses, payload.get("evidence_ids") or [])
    return {
        "research_id": "research_" + stable_hash({"title": payload["title"], "objective": payload["objective"]})[:16],
        "title": payload["title"],
        "objective": payload["objective"],
        "domain": domain,
        "status": "active",
        "research_organization": RESEARCH_ORGANIZATION,
        "research_questions": questions,
        "initial_hypotheses": hypotheses,
        "confidence": uncertainty["confidence"],
        "uncertainty": uncertainty,
        "events": ["RESEARCH_PROJECT_CREATED", "HYPOTHESIS_GENERATED"],
        "created_at": datetime.now(timezone.utc),
    }


def design_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") or [infer_primary_metric(payload.get("objective", ""), payload.get("hypothesis", ""))]
    variables = payload.get("variables") or ["intervention_enabled", "baseline_workflow"]
    controls = payload.get("controls") or ["same_team", "same_environment", "same_time_window"]
    datasets = payload.get("datasets") or ["historical_runtime_events", "mission_outcomes"]
    simulation_type = payload.get("simulation_type") or infer_simulation_type(payload.get("objective", ""), payload.get("hypothesis", ""))
    method = statistical_method(metrics, datasets)
    design = {
        "objective": payload["objective"],
        "hypothesis": payload["hypothesis"],
        "variables": variables,
        "controls": controls,
        "datasets": datasets,
        "metrics": metrics,
        "execution_plan": [
            "capture_baseline",
            "run_control_group",
            "run_treatment_or_simulation",
            "collect_evidence",
            "analyze_results",
            "peer_review",
        ],
        "stopping_criteria": ["minimum_sample_size_met", "no_critical_safety_incident", "confidence_interval_stable"],
        "ethical_constraints": payload.get("ethical_constraints") or ["do_not_expose_sensitive_data", "respect_user_consent"],
        "simulation_type": simulation_type,
    }
    reproducibility = {
        "datasets_recorded": bool(datasets),
        "parameters_recorded": True,
        "environment_recorded": True,
        "evaluation_scripts_required": True,
        "reproducibility_score": round(0.55 + min(0.25, len(datasets) * 0.05) + min(0.2, len(metrics) * 0.04), 3),
    }
    return {
        "experiment_id": "experiment_" + stable_hash({"hypothesis": payload["hypothesis"], "metrics": metrics})[:16],
        "research_id": payload.get("research_id"),
        "hypothesis_id": payload.get("hypothesis_id"),
        "design": design,
        "reproducibility": reproducibility,
        "statistical_plan": method,
        "status": "designed",
        "events": ["EXPERIMENT_STARTED"],
    }


def infer_simulation_type(objective: str, hypothesis: str) -> str:
    text = f"{objective} {hypothesis}".lower()
    if "migration" in text or "architecture" in text:
        return "architecture_simulation"
    if "cost" in text or "revenue" in text:
        return "financial_simulation"
    if "traffic" in text or "latency" in text or "performance" in text:
        return "performance_simulation"
    if "agent" in text or "workflow" in text:
        return "agent_simulation"
    return "system_simulation"


def statistical_method(metrics: list[str], datasets: list[str]) -> dict[str, Any]:
    metric_text = " ".join(metrics).lower()
    if "rate" in metric_text or "conversion" in metric_text:
        method = "two_proportion_test_with_confidence_interval"
    elif "time" in metric_text or "latency" in metric_text or "duration" in metric_text:
        method = "mann_whitney_or_bootstrapped_confidence_interval"
    elif len(datasets) > 1:
        method = "regression_with_sensitivity_analysis"
    else:
        method = "descriptive_statistics_with_effect_size"
    return {"method": method, "confidence_level": 0.95, "effect_size_required": True, "bias_controls": ["pre_registered_metrics", "independent_review"]}


def evaluate_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not evidence:
        return {
            "reliability": 0.0,
            "validity": 0.0,
            "reproducibility": 0.0,
            "novelty": 0.0,
            "impact": 0.0,
            "confidence": 0.0,
            "conclusion_strength": "insufficient_evidence",
        }
    dimensions = ("reliability", "validity", "reproducibility", "novelty", "impact")
    scores = {}
    for dim in dimensions:
        values = [float(item.get(dim, item.get("score", 0.5))) for item in evidence]
        scores[dim] = round(max(0.0, min(1.0, mean(values))), 3)
    scores["confidence"] = round(mean([scores["reliability"], scores["validity"], scores["reproducibility"], scores["impact"]]), 3)
    if scores["confidence"] >= 0.82:
        strength = "strong"
    elif scores["confidence"] >= 0.62:
        strength = "moderate"
    elif scores["confidence"] >= 0.38:
        strength = "weak"
    else:
        strength = "insufficient_evidence"
    scores["conclusion_strength"] = strength
    return scores


def synthesize_findings(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for item in memories:
        content = item.get("content", {})
        if isinstance(content, str):
            text = content
            linked = [str(item.get("id", ""))]
        else:
            text = " ".join([str(content.get("title", "")), str(content.get("objective", "")), str(content.get("summary", "")), str(content.get("conclusion", ""))])
            linked = [str(content.get("research_id") or item.get("id") or "")]
        evidence = content.get("evidence", []) if isinstance(content, dict) else []
        score = evaluate_evidence(evidence)
        themes = Counter(tokens(text)).most_common(6)
        finding_id = "finding_" + stable_hash({"text": text, "linked": linked})[:16]
        findings.append(
            {
                "finding_id": finding_id,
                "title": item.get("title") or "Research finding",
                "confidence": score["confidence"],
                "conclusion_strength": score["conclusion_strength"],
                "evidence_score": score,
                "known_facts": [word for word, _ in themes[:2]],
                "probable_findings": [text[:240]] if score["confidence"] >= 0.5 else [],
                "uncertain_areas": [] if score["confidence"] >= 0.7 else ["additional_evidence_required"],
                "unknown_questions": ["external_validity", "long_term_effect"] if score["confidence"] < 0.85 else [],
                "linked_items": [link for link in linked if link],
            }
        )
    return findings


def score_innovation(payload: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([payload.get("title", ""), str(payload.get("findings", "")), str(payload.get("evidence_ids", ""))]).lower()
    novelty = 0.72 if any(term in text for term in ("novel", "new", "invent", "algorithm", "architecture")) else 0.55
    business = 0.78 if any(term in text for term in ("revenue", "customer", "cost", "growth", "failure")) else 0.58
    merit = 0.8 if any(term in text for term in ("experiment", "evidence", "verified", "confidence")) else 0.52
    confidence = min(0.92, 0.45 + len(payload.get("evidence_ids") or []) * 0.08 + len(payload.get("findings") or []) * 0.06)
    implementation_cost = 0.42 if "workflow" in text or "standard" in text else 0.62
    strategic = 0.76 if any(term in text for term in ("strategy", "roadmap", "deployment", "reliability")) else 0.6
    priority = round((novelty * 0.18) + (business * 0.24) + (merit * 0.2) + (confidence * 0.2) + ((1 - implementation_cost) * 0.08) + (strategic * 0.1), 3)
    return {
        "novelty": round(novelty, 3),
        "business_value": round(business, 3),
        "technical_merit": round(merit, 3),
        "scientific_confidence": round(confidence, 3),
        "implementation_cost": round(implementation_cost, 3),
        "strategic_alignment": round(strategic, 3),
        "priority_score": priority,
    }


def build_publication(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings") or []
    evidence = payload.get("evidence_ids") or []
    score = score_innovation(payload)
    status = "needs_human_review" if payload.get("require_human_review", True) else "ready_for_internal_release"
    return {
        "publication_id": "publication_" + stable_hash({"title": payload["title"], "findings": findings})[:16],
        "title": payload["title"],
        "publication_type": payload.get("publication_type", "internal_report"),
        "status": status,
        "report": {
            "audience": payload.get("audience", "internal"),
            "executive_summary": publication_summary(payload),
            "finding_count": len(findings),
            "evidence_ids": evidence,
            "innovation_score": score,
            "uncertainty": "moderate" if len(evidence) < 3 else "low",
        },
        "review_workflow": [
            {"step": "AI review", "status": "completed"},
            {"step": "Independent AI review", "status": "queued"},
            {"step": "Human review", "status": "required" if payload.get("require_human_review", True) else "optional"},
            {"step": "Publication approval", "status": "pending"},
        ],
        "events": ["RESEARCH_REVIEW_COMPLETED", "PUBLICATION_RELEASED" if not payload.get("require_human_review", True) else "PUBLICATION_DRAFTED"],
    }


def publication_summary(payload: dict[str, Any]) -> str:
    findings = payload.get("findings") or []
    if findings:
        top = findings[0]
        if isinstance(top, dict):
            return f"{payload['title']} summarizes {len(findings)} finding(s), led by: {top.get('title') or top.get('conclusion') or 'research finding'}."
    return f"{payload['title']} is a research publication draft with traceable evidence and explicit uncertainty."
