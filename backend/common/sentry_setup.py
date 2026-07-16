import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration


def initialize_sentry(service_name: str) -> None:
    """Initialize Sentry for a backend service when a DSN is configured."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    app_release = os.getenv("APP_RELEASE", "development")
    git_sha = os.getenv("GIT_SHA")
    release = f"{app_release}+{git_sha[:8]}" if git_sha else app_release

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        release=release,
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", service_name)
