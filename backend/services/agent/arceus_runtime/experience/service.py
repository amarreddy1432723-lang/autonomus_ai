from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..compiler.utils import stable_hash


INTENT_KEYWORDS = {
    "execution": {"deploy", "rollback", "run", "execute", "start", "pause", "resume", "approve"},
    "review": {"review", "approve", "reject", "inspect", "check"},
    "planning": {"plan", "roadmap", "sprint", "architecture", "design", "prepare"},
    "analysis": {"analyze", "compare", "impact", "summarize", "explain", "why", "status", "progress", "progressing"},
    "automation": {"automate", "schedule", "trigger", "workflow", "incident"},
    "investigation": {"debug", "investigate", "failure", "outage", "error", "logs"},
    "learning": {"remember", "learn", "lesson", "standard", "preference"},
    "configuration": {"configure", "setting", "model", "provider", "account"},
    "information": {"show", "find", "search", "where", "list"},
}

HIGH_RISK_ACTIONS = {"deploy", "rollback", "delete", "payment", "production", "secret", "offboard", "approve deployment"}


def _id(prefix: str, payload: Any) -> str:
    return prefix + stable_hash(payload).replace("sha256:", "")[:18]


def classify_intent(objective: str) -> tuple[str, float]:
    lower = objective.lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in lower)
        for category, keywords in INTENT_KEYWORDS.items()
    }
    category, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    if score == 0:
        return "conversation", 0.52
    confidence = min(0.96, 0.62 + score * 0.11)
    return category, confidence


def extract_entities(objective: str, supplied: dict[str, Any] | None = None) -> dict[str, Any]:
    entities = dict(supplied or {})
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", objective)
    if quoted:
        entities.setdefault("quoted_subjects", quoted)
    repo_match = re.search(r"\b(?:repo|repository|project)\s+([A-Za-z0-9_.-]+)", objective, re.IGNORECASE)
    if repo_match:
        entities.setdefault("repository", repo_match.group(1))
    if "authentication" in objective.lower() or "auth" in objective.lower():
        entities.setdefault("domain", "authentication")
    if "deployment" in objective.lower() or "deploy" in objective.lower():
        entities.setdefault("environment", "deployment")
    if "yesterday" in objective.lower():
        entities.setdefault("time_range", "yesterday")
    return entities


def unified_context(user_id: str, *, scope: str = "mission") -> dict[str, Any]:
    return {
        "active_workspace": {
            "workspace_id": _id("ws_", user_id),
            "name": "Arceus Code Workspace",
            "scope": scope,
        },
        "current_mission": {
            "mission_id": "mission_auth_modernization",
            "title": "Authentication modernization",
            "status": "running",
            "progress": 0.68,
        },
        "repository": {"repository_id": "repo_arceus", "name": "arceus-code", "branch": "main"},
        "organization": {"organization_id": "org_engineering", "name": "Engineering Organization", "active_specialists": 7},
        "open_decisions": [
            {"decision_id": "dec_auth_sso", "title": "SSO architecture", "status": "approved"},
            {"decision_id": "dec_rollout", "title": "Deployment rollout", "status": "pending_review"},
        ],
        "reviews": [{"review_id": "rev_security_auth", "title": "Security review", "status": "pending"}],
        "memory": {
            "preferences": ["proof_first_receipts", "auto_apply_low_risk_changes"],
            "frequently_used_commands": ["Open Mission", "Review Code", "Search Knowledge"],
            "privacy": "personal memory never overrides enterprise policy",
        },
        "policies": ["human_authority", "verification_before_completion", "least_necessary_action"],
    }


def build_personal_workspace(user_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "workspace_id": _id("pws_", user_id),
        "owner_id": user_id,
        "organizations": [
            {"organization_id": "org_engineering", "name": "Engineering Organization", "status": "active"},
            {"organization_id": "org_product", "name": "Product Organization", "status": "ready"},
        ],
        "repositories": [{"repository_id": "repo_arceus", "name": "arceus-code", "status": "indexed"}],
        "dashboards": [{"dashboard_id": "mission_control", "name": "Mission Control"}, {"dashboard_id": "product_health", "name": "Product Health"}],
        "preferences": {"theme": "light", "reduced_motion": False, "primary_mode": "natural_language"},
        "memory": {"working_style": "proof_first", "notification_priority": "required_action_only"},
        "settings": {"sync": "enabled", "retention_days": 90, "voice": "available", "locale": "en-US"},
        "context": unified_context(user_id),
        "synced_at": now,
    }


def detect_intent(payload: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    objective = payload["objective"].strip()
    category, confidence = classify_intent(objective)
    entities = extract_entities(objective, payload.get("entities"))
    context = unified_context(user_id, scope=payload.get("context_scope", "mission"))
    risky = any(keyword in objective.lower() for keyword in HIGH_RISK_ACTIONS)
    permissions = ["mission.view", "knowledge.search"]
    suggested_action = "answer_with_context"
    if category == "execution":
        permissions.append("mission.start")
        suggested_action = "policy_check_then_execute" if risky else "execute_low_risk_action"
    elif category == "planning":
        permissions.append("mission.plan")
        suggested_action = "create_or_update_mission_plan"
    elif category == "review":
        permissions.append("approval.vote")
        suggested_action = "open_review_center"
    elif category in {"analysis", "information"}:
        suggested_action = "retrieve_context_and_summarize"

    return {
        "intent_id": _id("intent_", {"objective": objective, "user": user_id, "mode": payload.get("mode", "chat")}),
        "objective": objective,
        "category": category,
        "entities": entities,
        "confidence": confidence,
        "constraints": payload.get("constraints") or [],
        "context": {
            "scope": payload.get("context_scope", "mission"),
            "active_workspace": context["active_workspace"]["workspace_id"],
            "current_mission": context["current_mission"]["mission_id"] if context["current_mission"] else None,
            "repository": context["repository"]["name"] if context["repository"] else None,
        },
        "permissions": permissions,
        "suggested_action": suggested_action,
        "explainability": {
            "objective": objective,
            "inputs": ["objective", "mode", "unified_context", "policy_keywords"],
            "evidence": ["active_mission", "repository", "open_decisions"],
            "tradeoffs": ["speed_vs_human_authority"] if risky else ["low_cognitive_load_vs_detail"],
            "risks": ["requires_confirmation"] if risky else [],
            "verification": ["permission_check", "policy_check"],
            "confidence_reason": "keyword and context based deterministic classification",
        },
    }


def execute_intent(payload: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    intent = detect_intent(payload, user_id=user_id)
    risky = bool(intent["explainability"]["risks"])
    accepted = not risky or payload.get("mode") in {"command", "workflow"}
    status = "requires_confirmation" if risky and not accepted else "accepted"
    thread_id = _id("thread_", {"intent": intent["intent_id"], "mission": intent["context"].get("current_mission")})
    return {
        "intent": intent,
        "accepted": accepted,
        "status": status,
        "mission_thread": {
            "thread_id": thread_id,
            "type": "mission_thread",
            "linked_mission_id": intent["context"].get("current_mission"),
            "participants": ["user", "mission_lead", "relevant_specialists"],
        },
        "verification": {
            "policy_checked": True,
            "requires_human_confirmation": risky,
            "recoverable": True,
            "interruptible": True,
        },
        "response": {
            "summary": _response_summary(intent, status),
            "next_actions": _next_actions(intent, risky),
        },
        "events": ["INTENT_RECEIVED", "MISSION_OPENED"] + (["HUMAN_APPROVAL_REQUESTED"] if risky else []),
    }


def _response_summary(intent: dict[str, Any], status: str) -> str:
    if status == "requires_confirmation":
        return f"I understood this as {intent['category']} and need confirmation before acting."
    if intent["category"] == "analysis":
        return "I found the active mission context and can summarize progress with evidence."
    if intent["category"] == "planning":
        return "I can turn this into a mission plan linked to repository knowledge and decisions."
    return f"I understood this as {intent['category']} and prepared the next step."


def _next_actions(intent: dict[str, Any], risky: bool) -> list[str]:
    if risky:
        return ["Review policy impact", "Confirm action", "Open related mission"]
    if intent["category"] in {"analysis", "information"}:
        return ["Show evidence", "Open mission thread", "Search knowledge"]
    if intent["category"] == "planning":
        return ["Draft plan", "Choose specialists", "Set approval gates"]
    return ["Continue", "Open workspace"]


def timeline() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    return [
        {
            "item_id": "tl_decision_auth_sso",
            "occurred_at": now - timedelta(hours=3),
            "event_type": "decision",
            "title": "SSO architecture approved",
            "summary": "Engineering selected OIDC-first authentication with enterprise policy checks.",
            "related_mission_id": "mission_auth_modernization",
            "priority": "normal",
            "required_action": None,
        },
        {
            "item_id": "tl_review_security",
            "occurred_at": now - timedelta(hours=1),
            "event_type": "review",
            "title": "Security review pending",
            "summary": "Deployment cannot proceed until the security reviewer signs off.",
            "related_mission_id": "mission_auth_modernization",
            "priority": "high",
            "required_action": "review_security_findings",
        },
        {
            "item_id": "tl_verification",
            "occurred_at": now - timedelta(minutes=15),
            "event_type": "verification",
            "title": "Build evidence collected",
            "summary": "Runtime tests passed and evidence was attached to the mission thread.",
            "related_mission_id": "mission_auth_modernization",
            "priority": "normal",
            "required_action": None,
        },
    ]


def dashboard(role: str = "developer") -> dict[str, Any]:
    widgets = [
        {"widget_key": "active_missions", "title": "Active Missions", "value": "3", "status": "healthy", "action": "Open Mission"},
        {"widget_key": "pending_reviews", "title": "Pending Reviews", "value": "1", "status": "needs_action", "action": "Review"},
        {"widget_key": "ai_activity", "title": "AI Activity", "value": "7 specialists", "status": "active", "action": "View Organization"},
        {"widget_key": "costs", "title": "Costs", "value": "$24.80", "status": "within_budget", "action": "Open Budget"},
    ]
    if role == "sre":
        widgets.append({"widget_key": "incidents", "title": "Incidents", "value": "0 critical", "status": "healthy", "action": "Open Operations"})
    return {
        "dashboard_id": _id("dash_", role),
        "role": role,
        "generated_at": datetime.now(timezone.utc),
        "widgets": widgets,
        "notifications": [
            {
                "notification_id": "notif_security_review",
                "priority": "high",
                "required_action": "Review",
                "impact": "Blocks deployment",
                "related_mission_id": "mission_auth_modernization",
                "suggested_response": "Open security review",
            }
        ],
        "accessibility": {"keyboard_navigation": True, "screen_reader_labels": True, "reduced_motion_supported": True},
        "localization": {"timezone": "UTC", "locale": "en-US", "currency": "USD"},
    }


def voice_response(payload: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    intent = detect_intent(
        {
            "objective": payload["transcript"],
            "mode": "voice",
            "context_scope": payload.get("context_scope", "mission"),
            "entities": {"locale": payload.get("locale"), "device": payload.get("device")},
        },
        user_id=user_id,
    )
    risky = bool(intent["explainability"]["risks"])
    spoken = "I can do that after confirmation." if risky else _response_summary(intent, "accepted")
    return {
        "transcript": payload["transcript"],
        "intent": intent,
        "spoken_response": spoken,
        "command_safe_to_execute": not risky,
        "requires_confirmation": risky,
    }


def smart_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload["query"]
    scopes = payload.get("scopes") or ["missions", "knowledge", "decisions", "incidents", "code"]
    category, _ = classify_intent(query)
    results = []
    for index, scope in enumerate(scopes, start=1):
        results.append(
            {
                "result_id": _id("sr_", {"query": query, "scope": scope}),
                "title": f"{scope.title()} match for {query[:48]}",
                "scope": scope,
                "summary": f"Relevant {scope} context connected to the active workspace.",
                "relevance": round(max(0.35, 0.96 - index * 0.08), 2),
                "related_intent": category,
                "action": "open_result" if scope != "knowledge" else "search_knowledge_graph",
            }
        )
    return {
        "query": query,
        "scopes": scopes,
        "strategy": ["intent_detection", "unified_context", "keyword", "knowledge_graph"],
        "results": results[: int(payload.get("limit", 10))],
        "completed_at": datetime.now(timezone.utc),
    }
