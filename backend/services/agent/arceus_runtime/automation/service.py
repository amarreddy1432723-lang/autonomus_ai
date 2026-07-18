from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..compiler.utils import stable_hash


RISKY_KEYWORDS = {
    "deploy": "high",
    "delete": "high",
    "payment": "high",
    "invoice": "high",
    "offboard": "critical",
    "production": "critical",
    "secret": "critical",
    "cve": "critical",
    "incident": "high",
    "migration": "high",
}

DOMAIN_ORGANIZATIONS = {
    "engineering": {
        "specialists": ["Engineering Manager", "Backend Engineer", "Frontend Engineer", "QA Reviewer", "Security Reviewer"],
        "policies": ["verification_before_completion", "implementer_cannot_self_approve"],
        "connectors": ["github", "ci_cd", "sentry"],
        "autonomy_ceiling": "L3",
    },
    "devops": {
        "specialists": ["SRE", "Cloud Architect", "Database Administrator", "Security Reviewer", "Release Manager"],
        "policies": ["deploy_only_after_verification", "rollback_plan_required"],
        "connectors": ["cloud_provider", "monitoring", "ci_cd"],
        "autonomy_ceiling": "L2",
    },
    "customer_support": {
        "specialists": ["Support Engineer", "Escalation Lead", "Knowledge Analyst", "Engineering Liaison"],
        "policies": ["customer_data_minimization", "human_review_for_refunds"],
        "connectors": ["ticketing", "crm", "email"],
        "autonomy_ceiling": "L3",
    },
    "finance": {
        "specialists": ["Finance Analyst", "Billing Specialist", "Business Reviewer"],
        "policies": ["approval_required_over_10000", "audit_every_payment_change"],
        "connectors": ["stripe", "erp"],
        "autonomy_ceiling": "L1",
    },
    "cybersecurity": {
        "specialists": ["Security Analyst", "Incident Commander", "Forensics Specialist", "Communications Lead"],
        "policies": ["critical_cve_immediate_mission", "no_secret_exfiltration", "human_authority_for_containment"],
        "connectors": ["sentry", "siem", "identity_provider"],
        "autonomy_ceiling": "L2",
    },
}

DEFAULT_TEMPLATES = {
    "incident_response": {
        "template_key": "incident_response",
        "name": "Incident Response",
        "domain": "devops",
        "objectives": ["classify impact", "diagnose root cause", "mitigate safely", "verify recovery", "produce postmortem"],
        "required_specialists": ["Incident Commander", "SRE", "Database Specialist", "Security Reviewer", "Communications Lead"],
        "tasks": ["triage alert", "analyze impact", "identify likely causes", "propose mitigation", "verify service health", "write postmortem"],
        "approval_gates": ["mitigation_approval", "production_change_approval"],
        "rollback_required": True,
        "version": 1,
    },
    "release": {
        "template_key": "release",
        "name": "Release",
        "domain": "engineering",
        "objectives": ["validate release readiness", "coordinate rollout", "monitor health", "capture lessons"],
        "required_specialists": ["Release Manager", "QA Reviewer", "Security Reviewer", "SRE"],
        "tasks": ["verify checks", "prepare release notes", "confirm rollback", "deploy canary", "monitor metrics"],
        "approval_gates": ["release_approval"],
        "rollback_required": True,
        "version": 1,
    },
    "security_audit": {
        "template_key": "security_audit",
        "name": "Security Audit",
        "domain": "cybersecurity",
        "objectives": ["identify vulnerabilities", "assess exploitability", "recommend remediation", "verify fixes"],
        "required_specialists": ["Security Analyst", "Backend Engineer", "Dependency Reviewer", "Compliance Reviewer"],
        "tasks": ["scan dependencies", "review auth paths", "inspect secrets exposure", "create remediation plan"],
        "approval_gates": ["security_review"],
        "rollback_required": False,
        "version": 1,
    },
    "customer_escalation": {
        "template_key": "customer_escalation",
        "name": "Customer Escalation",
        "domain": "customer_support",
        "objectives": ["understand customer issue", "coordinate engineering response", "communicate next steps"],
        "required_specialists": ["Support Engineer", "Customer Success Analyst", "Engineering Liaison"],
        "tasks": ["summarize ticket", "classify severity", "find related incidents", "propose response"],
        "approval_gates": ["customer_communication_approval"],
        "rollback_required": False,
        "version": 1,
    },
}


def _short_hash(payload: Any, prefix: str) -> str:
    return prefix + stable_hash(payload).replace("sha256:", "")[:18]


def infer_risk(*values: str) -> str:
    text = " ".join(values).lower()
    severity = "low"
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for keyword, risk in RISKY_KEYWORDS.items():
        if keyword in text and order[risk] > order[severity]:
            severity = risk
    if severity == "low" and any(word in text for word in ["change", "update", "execute", "workflow"]):
        return "medium"
    return severity


def autonomy_rank(level: str) -> int:
    return {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}.get(level, 0)


def evaluate_automation_policy(*, autonomy_level: str, risk_level: str, dry_run: bool, template: dict[str, Any]) -> dict[str, Any]:
    required_approvals = list(template.get("approval_gates") or [])
    if risk_level in {"high", "critical"}:
        required_approvals.extend(["human_operator", "security_reviewer"])
    if template.get("rollback_required"):
        required_approvals.append("rollback_plan_review")
    required_approvals = sorted(set(required_approvals))

    if dry_run:
        decision = "simulate"
        accepted = True
        reason = "Dry run accepted; no external systems will be changed."
    elif risk_level == "critical":
        decision = "needs_human_approval"
        accepted = False
        reason = "Critical automation requires explicit human approval."
    elif risk_level == "high" and autonomy_rank(autonomy_level) < 4:
        decision = "needs_human_approval"
        accepted = False
        reason = "High-risk automation requires approval unless autonomy is L4 and policy allows it."
    elif autonomy_rank(autonomy_level) < 2:
        decision = "recommend_only"
        accepted = False
        reason = "Autonomy level only permits recommendations."
    else:
        decision = "accepted"
        accepted = True
        reason = "Automation is within autonomy and policy boundaries."

    return {
        "accepted": accepted,
        "decision": decision,
        "reason": reason,
        "required_approvals": required_approvals,
        "rollback_required": bool(template.get("rollback_required")),
    }


def template_catalog() -> list[dict[str, Any]]:
    return list(DEFAULT_TEMPLATES.values())


def register_template(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_key": payload["template_key"],
        "name": payload["name"],
        "domain": payload["domain"],
        "objectives": payload["objectives"],
        "required_specialists": payload["required_specialists"],
        "tasks": payload["tasks"],
        "approval_gates": payload.get("approval_gates") or [],
        "rollback_required": bool(payload.get("rollback_required", True)),
        "version": 1,
    }


def get_template(template_key: str, domain: str | None = None) -> dict[str, Any]:
    template = DEFAULT_TEMPLATES.get(template_key)
    if template:
        return dict(template)
    fallback_domain = domain or "engineering"
    return {
        "template_key": template_key,
        "name": template_key.replace("_", " ").title(),
        "domain": fallback_domain,
        "objectives": ["understand objective", "plan workflow", "execute safely", "verify outcome", "record lessons"],
        "required_specialists": organization_for_domain(fallback_domain)["specialists"][:4],
        "tasks": ["classify request", "compile workflow", "evaluate policy", "prepare execution", "collect evidence"],
        "approval_gates": ["human_review"],
        "rollback_required": True,
        "version": 1,
    }


def organization_for_domain(domain: str) -> dict[str, Any]:
    base = DOMAIN_ORGANIZATIONS.get(domain) or {
        "specialists": ["Mission Lead", "Domain Specialist", "Policy Reviewer", "QA Reviewer"],
        "policies": ["human_authority", "audit_required"],
        "connectors": ["tool_gateway"],
        "autonomy_ceiling": "L2",
    }
    return {"organization_key": f"{domain}_organization", "domain": domain, **base}


def list_organizations() -> list[dict[str, Any]]:
    domains = [
        "engineering",
        "devops",
        "it_operations",
        "customer_support",
        "sales",
        "marketing",
        "finance",
        "legal",
        "human_resources",
        "compliance",
        "cybersecurity",
        "data_engineering",
        "business_intelligence",
        "operations",
        "procurement",
    ]
    return [organization_for_domain(domain) for domain in domains]


def compile_workflow(*, objective: str, domain: str, template_key: str, trigger_id: str | None = None) -> dict[str, Any]:
    template = get_template(template_key, domain)
    organization = organization_for_domain(domain)
    workflow_id = _short_hash({"objective": objective, "domain": domain, "template": template_key, "trigger": trigger_id}, "wf_")
    return {
        "workflow_id": workflow_id,
        "objective": objective,
        "domain": domain,
        "template_key": template["template_key"],
        "objectives": template["objectives"],
        "tasks": [
            {"task_key": f"{workflow_id}.{index}", "title": task, "owner": organization["specialists"][index % len(organization["specialists"])]}
            for index, task in enumerate(template["tasks"], start=1)
        ],
        "dependencies": [{"before": template["tasks"][index - 1], "after": template["tasks"][index]} for index in range(1, len(template["tasks"]))],
        "required_specialists": template["required_specialists"],
        "approval_gates": template["approval_gates"],
    }


def connector_plan(connector_keys: list[str], domain: str) -> list[dict[str, Any]]:
    organization = organization_for_domain(domain)
    keys = connector_keys or organization["connectors"]
    return [
        {
            "connector_id": key,
            "provider": key,
            "capabilities": ["read", "propose", "execute_via_tool_gateway"],
            "authentication": "scoped_token_or_oauth",
            "scopes": [f"{domain}:read", f"{domain}:write:approved"],
            "rate_limits": {"requests_per_minute": 60},
            "health": "configured" if key in organization["connectors"] else "needs_setup",
        }
        for key in keys
    ]


def create_trigger(payload: dict[str, Any]) -> dict[str, Any]:
    risk_level = infer_risk(payload.get("condition", ""), payload.get("source", ""), str(payload.get("payload", {})))
    template = get_template(payload["mission_template"], payload["domain"])
    policy = evaluate_automation_policy(
        autonomy_level=payload.get("autonomy_level", "L2"),
        risk_level=risk_level,
        dry_run=bool(payload.get("dry_run", True)),
        template=template,
    )
    trigger_id = _short_hash(payload, "trg_")
    workflow = compile_workflow(
        objective=f"Respond to {payload['source']} trigger: {payload['condition']}",
        domain=payload["domain"],
        template_key=payload["mission_template"],
        trigger_id=trigger_id,
    )
    mission = {
        "mission_id": _short_hash({"trigger_id": trigger_id, "workflow": workflow["workflow_id"]}, "auto_msn_"),
        "title": workflow["objective"],
        "domain": payload["domain"],
        "status": "ready" if policy["accepted"] else "awaiting_approval",
        "workflow_id": workflow["workflow_id"],
        "required_specialists": workflow["required_specialists"],
    }
    return {
        "trigger_id": trigger_id,
        "trigger_type": payload["trigger_type"],
        "source": payload["source"],
        "condition": payload["condition"],
        "domain": payload["domain"],
        "mission_template": payload["mission_template"],
        "risk_level": risk_level,
        "accepted": policy["accepted"],
        "status": "mission_generated" if policy["accepted"] else "approval_required",
        "policy_decision": policy,
        "generated_mission": mission,
        "events": ["AUTOMATION_TRIGGERED", "MISSION_GENERATED"] + ([] if policy["accepted"] else ["HUMAN_APPROVAL_REQUESTED"]),
        "created_at": datetime.now(timezone.utc),
    }


def execute_automation(payload: dict[str, Any]) -> dict[str, Any]:
    template = get_template(payload["template_key"], payload["domain"])
    policy = evaluate_automation_policy(
        autonomy_level=payload.get("autonomy_level", "L2"),
        risk_level=payload.get("risk_level", "medium"),
        dry_run=bool(payload.get("dry_run", True)),
        template=template,
    )
    workflow = compile_workflow(objective=payload["objective"], domain=payload["domain"], template_key=payload["template_key"])
    accepted = policy["accepted"]
    status = "simulated" if payload.get("dry_run", True) else "started" if accepted else "blocked_by_policy"
    return {
        "execution_id": _short_hash(payload, "auto_exec_"),
        "accepted": accepted,
        "status": status,
        "autonomy_level": payload.get("autonomy_level", "L2"),
        "risk_level": payload.get("risk_level", "medium"),
        "policy_decision": policy,
        "workflow": workflow,
        "connector_plan": connector_plan(payload.get("connector_keys") or [], payload["domain"]),
        "required_approvals": policy["required_approvals"],
        "audit_events": ["WORKFLOW_STARTED"] if accepted else ["POLICY_BLOCKED", "HUMAN_APPROVAL_REQUESTED"],
        "created_at": datetime.now(timezone.utc),
    }


def active_automation_missions() -> list[dict[str, Any]]:
    return [
        {
            "mission_id": "auto_msn_database_latency",
            "title": "Database latency above 500ms",
            "domain": "devops",
            "status": "awaiting_approval",
            "autonomy_level": "L2",
            "risk_level": "high",
            "owner_organization": "devops_organization",
            "generated_from": "monitoring:database_latency",
            "workflow_steps": get_template("incident_response")["tasks"],
        },
        {
            "mission_id": "auto_msn_release_readiness",
            "title": "Weekly release readiness review",
            "domain": "engineering",
            "status": "ready",
            "autonomy_level": "L3",
            "risk_level": "medium",
            "owner_organization": "engineering_organization",
            "generated_from": "schedule:weekly",
            "workflow_steps": get_template("release")["tasks"],
        },
    ]


def automation_dashboard() -> dict[str, Any]:
    missions = active_automation_missions()
    policy_violations = sum(1 for mission in missions if mission["status"] == "awaiting_approval" and mission["risk_level"] in {"high", "critical"})
    return {
        "generated_at": datetime.now(timezone.utc),
        "automation_coverage": 0.42,
        "human_intervention_rate": 0.31,
        "sla_compliance": 0.97,
        "success_rate": 0.91,
        "cost_reduction": 0.18,
        "error_reduction": 0.22,
        "active_missions": len(missions),
        "policy_violations": policy_violations,
        "organizations": list_organizations()[:5],
        "recommendations": [
            "connect_monitoring_provider_for_incident_triggers",
            "review_high_risk_automation_approval_queue",
            "increase_L3_coverage_for_low_risk_release_checks",
        ],
    }
