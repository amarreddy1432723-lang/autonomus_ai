from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_gate_script_blocks_without_required_provider_inputs():
    script = (ROOT / "scripts" / "verify-release-gate.ps1").read_text(encoding="utf-8")

    for token in [
        "verify-provider-config.ps1",
        "RAILWAY_TOKEN",
        "SMOKE_BACKEND_URL",
        "SMOKE_FRONTEND_URL",
        "SMOKE_ADMIN_USER_ID",
        "backup-postgres.ps1",
        "restore-postgres.ps1",
        "deploy-railway.ps1",
        "smoke-test.ps1",
        "release-gate-summary.json",
    ]:
        assert token in script

    assert 'ValidateSet("predeploy", "postdeploy")' in script
    assert "Release gate blocked" in script


def test_release_workflow_runs_gate_before_railway_deploy():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    deploy = (ROOT / "scripts" / "deploy-railway.ps1").read_text(encoding="utf-8")

    assert "Pre-deploy release gate" in workflow
    assert "verify-release-gate.ps1" in workflow
    assert workflow.index("Pre-deploy release gate") < workflow.index("Deploy Railway project")
    assert "GITHUB_APP_PRIVATE_KEY" in workflow
    assert "STRIPE_WEBHOOK_SECRET" in workflow
    assert "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" in workflow

    assert "SkipReleaseGate" in deploy
    assert "verify-release-gate.ps1" in deploy
