from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from services.agent.arceus_runtime.deployment.api_schemas import DriftReportRequest
from services.agent.arceus_runtime.deployment.service import (
    migration_plan_for,
    plan_deployment,
    record_drift,
    risk_score_for,
    traffic_plan_for,
)
from services.shared.arceus_core_models import (
    ArceusDeploymentArtifact,
    ArceusDeploymentDriftReport,
    ArceusDeploymentEnvironment,
    ArceusDeploymentPlan,
    ArceusDeploymentRelease,
    ArceusDeploymentRequest,
    ArceusDeploymentTarget,
)


def test_canary_traffic_plan_requires_first_production_approval() -> None:
    plan = traffic_plan_for(strategy="canary", environment_type="production")

    assert [stage["newReleasePercentage"] for stage in plan["stages"]] == [5, 25, 100]
    assert plan["stages"][0]["manualApprovalRequired"] is True
    assert plan["rollbackOnViolation"] is True


def test_destructive_production_migration_is_critical_and_requires_backup() -> None:
    plan = migration_plan_for({"migration": {"destructive": True, "rollback_supported": False}}, env_type="production")

    assert plan["required"] is True
    assert plan["risk"] == "critical"
    assert plan["backup_required"] is True
    assert plan["rollback_supported"] is False


def test_risk_score_increases_for_production_recreate_and_unsigned_artifacts() -> None:
    environment = SimpleNamespace(environment_type="production", protection_level="critical")
    artifacts = [SimpleNamespace(signed=False), SimpleNamespace(signed=True)]

    score = risk_score_for(
        environment=environment,
        strategy="recreate",
        artifacts=artifacts,
        migration_plan={"risk": "high"},
        blockers=["missing scan"],
        warnings=["provider limitation"],
    )

    assert score >= 90


def test_deployment_plan_blocks_unapproved_unsigned_production_release() -> None:
    tenant_id = uuid4()
    release_id = uuid4()
    environment_id = uuid4()
    target_id = uuid4()
    request_id = uuid4()

    db = _FakeDb(
        {
            ArceusDeploymentRequest: [
                SimpleNamespace(id=request_id, release_id=release_id, environment_id=environment_id, strategy="rolling", status="requested", dry_run=False)
            ],
            ArceusDeploymentRelease: [
                SimpleNamespace(id=release_id, status="draft", provenance={"builder_trusted": True}, version="1.0.0")
            ],
            ArceusDeploymentEnvironment: [
                SimpleNamespace(id=environment_id, target_id=target_id, status="ready", environment_type="production", protection_level="critical", current_release_id=None, name="Production", metadata_json={}, ttl_expires_at=None)
            ],
            ArceusDeploymentTarget: [
                SimpleNamespace(id=target_id, provider_type="railway", capabilities={"canary": False, "blueGreen": False})
            ],
            ArceusDeploymentArtifact: [
                SimpleNamespace(id=uuid4(), release_id=release_id, digest="sha256:abc", signed=False, scan_status="pending")
            ],
        }
    )

    plan = plan_deployment(db, tenant_id=tenant_id, deployment_request_id=request_id)

    assert plan.deployable is False
    assert plan.estimated_cost_cents == Decimal("130.000000")
    assert "Production release must be approved or deployable." in plan.blockers
    assert "Production deployment requires signed artifacts." in plan.blockers
    assert "Production deployment requires completed artifact security scans." in plan.blockers
    assert any(isinstance(item, ArceusDeploymentPlan) for item in db.added)


def test_deployment_plan_allows_signed_verified_preview_release() -> None:
    tenant_id = uuid4()
    release_id = uuid4()
    environment_id = uuid4()
    target_id = uuid4()
    request_id = uuid4()

    db = _FakeDb(
        {
            ArceusDeploymentRequest: [
                SimpleNamespace(id=request_id, release_id=release_id, environment_id=environment_id, strategy="rolling", status="requested", dry_run=False)
            ],
            ArceusDeploymentRelease: [
                SimpleNamespace(id=release_id, status="verified", provenance={"builder_trusted": True}, version="1.0.0-preview")
            ],
            ArceusDeploymentEnvironment: [
                SimpleNamespace(id=environment_id, target_id=target_id, status="ready", environment_type="preview", protection_level="standard", current_release_id=None, name="Preview", metadata_json={"health_url": "/api/health"}, ttl_expires_at=None)
            ],
            ArceusDeploymentTarget: [
                SimpleNamespace(id=target_id, provider_type="railway", capabilities={"canary": False, "blueGreen": False})
            ],
            ArceusDeploymentArtifact: [
                SimpleNamespace(id=uuid4(), release_id=release_id, digest="sha256:def", signed=True, scan_status="passed")
            ],
        }
    )

    plan = plan_deployment(db, tenant_id=tenant_id, deployment_request_id=request_id)

    assert plan.deployable is True
    assert plan.blockers == []
    assert plan.health_verification_plan["checks"][0]["target"] == "/api/health"


def test_drift_report_resolves_when_desired_and_actual_hashes_match() -> None:
    db = _FakeDb({})
    environment_id = uuid4()

    report = record_drift(
        db,
        tenant_id=uuid4(),
        payload=DriftReportRequest(
            environment_id=environment_id,
            drift_type="configuration",
            desired_hash="abcdef123456",
            actual_hash="abcdef123456",
            severity="low",
            findings=[],
        ),
    )

    assert isinstance(report, ArceusDeploymentDriftReport)
    assert report.status == "resolved"


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
