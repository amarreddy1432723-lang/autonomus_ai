from pathlib import Path


def test_provider_verifier_covers_required_external_systems():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "verify-provider-config.ps1").read_text(encoding="utf-8")
    template = (root / ".env.production.example").read_text(encoding="utf-8")

    for token in [
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
        "CLERK_JWKS_URL",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "SENTRY_DSN",
        "RAILWAY_TOKEN",
        "WIN_CSC_LINK",
        "APPLE_TEAM_ID",
    ]:
        assert token in script
        assert token in template

    assert "ALLOW_DEMO_USER" in script
    assert "ALLOW_DEV_AUTH_FALLBACK" in script
    assert "NEXT_PUBLIC_REQUIRE_AUTH" in script
    assert "provider configuration blocker" in script
