from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.agent.arceus_runtime.security.api_schemas import (
    SecurityAssetRequest,
    SecurityFindingRequest,
    SecurityGateRequest,
    SecurityResponseActionRequest,
)
from services.agent.arceus_runtime.security.service import (
    calculate_risk_score,
    create_response_action,
    evaluate_security_gate,
    normalize_finding,
    upsert_security_asset,
)
from services.shared.arceus_core_models import (
    ArceusSecurityAsset,
    ArceusSecurityException,
    ArceusSecurityFinding,
    ArceusSecurityResponseAction,
    ArceusSecurityRiskScore,
)


def test_asset_upsert_reuses_external_reference() -> None:
    tenant_id = uuid4()
    existing = ArceusSecurityAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        asset_type="service",
        external_reference="railway:agent",
        name="Agent",
        criticality="high",
        internet_exposed=True,
    )
    db = _FakeDb({ArceusSecurityAsset: [existing]})

    item = upsert_security_asset(
        db,
        tenant_id=tenant_id,
        payload=SecurityAssetRequest(
            asset_type="service",
            external_reference="railway:agent",
            name="Agent Service",
            criticality="critical",
            internet_exposed=True,
            environment_type="production",
            data_classifications=["restricted"],
        ),
    )

    assert item.id == existing.id
    assert item.name == "Agent Service"
    assert item.criticality == "critical"


def test_finding_normalization_deduplicates_by_stable_fingerprint() -> None:
    tenant_id = uuid4()
    asset_id = uuid4()
    db = _FakeDb({ArceusSecurityFinding: []})
    payload = SecurityFindingRequest(
        asset_id=asset_id,
        source="semgrep",
        source_finding_id="rule-1",
        category="vulnerability",
        title="Command injection risk",
        severity="high",
        affected_component="sandbox.py",
        location={"file": "sandbox.py", "line": 42},
        enrichment={"rule_id": "python.command-injection"},
    )

    first, created = normalize_finding(db, tenant_id=tenant_id, payload=payload)
    db.mapping[ArceusSecurityFinding] = [first]
    second, second_created = normalize_finding(db, tenant_id=tenant_id, payload=payload)

    assert created is True
    assert second_created is False
    assert first.id == second.id
    assert first.fingerprint == second.fingerprint


def test_secret_findings_reject_raw_secret_values() -> None:
    payload = SecurityFindingRequest(
        asset_id=uuid4(),
        source="secret-scanner",
        category="secret_exposure",
        title="API key exposed",
        severity="critical",
        enrichment={"provider": "openai", "secret_value": "sk-live-never-store-this"},
    )

    with pytest.raises(ValueError, match="RAW_SECRET_VALUES_NOT_ALLOWED"):
        normalize_finding(_FakeDb({}), tenant_id=uuid4(), payload=payload)


def test_contextual_risk_scores_production_exposed_sensitive_assets_as_emergency() -> None:
    tenant_id = uuid4()
    asset_id = uuid4()
    finding_id = uuid4()
    asset = SimpleNamespace(id=asset_id, criticality="critical", internet_exposed=True, data_classifications=["restricted"])
    finding = SimpleNamespace(
        id=finding_id,
        asset_id=asset_id,
        severity="critical",
        enrichment={"known_exploited": True, "reachable": True, "active_exploitation": True, "privilege_impact_score": 25},
    )
    db = _FakeDb({ArceusSecurityAsset: [asset]})

    score = calculate_risk_score(db, tenant_id=tenant_id, finding=finding)

    assert score.total_score == 100
    assert score.risk_level == "emergency"
    assert score.explanation["internet_exposed"] is True


def test_security_gate_blocks_critical_findings_without_active_exception() -> None:
    tenant_id = uuid4()
    asset_id = uuid4()
    finding_id = uuid4()
    finding = SimpleNamespace(id=finding_id, asset_id=asset_id, title="Production secret exposed", severity="critical", status="open")
    score = SimpleNamespace(finding_id=finding_id, risk_level="critical", calculated_at=datetime.now(timezone.utc))
    db = _FakeDb({ArceusSecurityFinding: [finding], ArceusSecurityRiskScore: [score], ArceusSecurityException: []})

    decision = evaluate_security_gate(
        db,
        tenant_id=tenant_id,
        payload=SecurityGateRequest(gate_type="deployment", asset_ids=[asset_id], environment_type="production"),
    )

    assert decision.decision == "block"
    assert decision.blockers[0]["risk_level"] == "critical"
    assert "create_remediation_mission" in decision.obligations


def test_security_gate_honors_active_exception() -> None:
    tenant_id = uuid4()
    asset_id = uuid4()
    finding_id = uuid4()
    finding = SimpleNamespace(id=finding_id, asset_id=asset_id, title="Accepted risk", severity="critical", status="open")
    exception = SimpleNamespace(finding_id=finding_id, status="active", expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    db = _FakeDb({ArceusSecurityFinding: [finding], ArceusSecurityException: [exception], ArceusSecurityRiskScore: []})

    decision = evaluate_security_gate(
        db,
        tenant_id=tenant_id,
        payload=SecurityGateRequest(gate_type="release", asset_ids=[asset_id], environment_type="production"),
    )

    assert decision.decision == "allow"
    assert decision.blockers == []


def test_response_actions_only_auto_allow_reversible_containment() -> None:
    tenant_id = uuid4()
    safe = create_response_action(
        _FakeDb({}),
        tenant_id=tenant_id,
        payload=SecurityResponseActionRequest(
            action_type="pause_mission",
            target_id="mission-1",
            risk_level="high",
            trace_id="trace-1",
            idempotency_key="idem-safe-1",
        ),
    )
    risky = create_response_action(
        _FakeDb({}),
        tenant_id=tenant_id,
        payload=SecurityResponseActionRequest(
            action_type="rotate_secret",
            target_id="secret-1",
            risk_level="critical",
            trace_id="trace-2",
            idempotency_key="idem-risky-1",
        ),
    )

    assert isinstance(safe, ArceusSecurityResponseAction)
    assert safe.automatic_allowed is True
    assert safe.execution_status == "queued"
    assert risky.automatic_allowed is False
    assert risky.approval_status == "pending"
    assert risky.execution_status == "blocked"


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *_args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)


class _FakeDb:
    def __init__(self, mapping) -> None:
        self.mapping = mapping
        self.added = []

    def query(self, model):
        return _Query(self.mapping.get(model, []))

    def add(self, item) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.added.append(item)

    def flush(self) -> None:
        return None
