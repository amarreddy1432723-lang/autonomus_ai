from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import Organization


def _org_by_slug(db: Session, org_slug: str) -> Organization:
    org = db.query(Organization).filter(Organization.slug == org_slug, Organization.status == "active").first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def enterprise_sso_status(db: Session, org_slug: str) -> dict:
    org = _org_by_slug(db, org_slug)
    sso = (org.settings_json or {}).get("sso") or {}
    provider = str(sso.get("provider") or "").lower()
    return {
        "organization": {"id": str(org.id), "name": org.name, "slug": org.slug},
        "enabled": bool(sso.get("enabled") and provider in {"oidc", "saml"}),
        "provider": provider or None,
        "jit_provisioning": bool(sso.get("jit_provisioning", True)),
    }


def build_sso_initiate_response(db: Session, org_slug: str, frontend_url: str) -> dict:
    org = _org_by_slug(db, org_slug)
    sso = (org.settings_json or {}).get("sso") or {}
    provider = str(sso.get("provider") or "").lower()
    if not sso.get("enabled") or provider not in {"oidc", "saml"}:
        raise HTTPException(status_code=400, detail="Enterprise SSO is not configured for this organization")

    if provider == "saml":
        metadata_url = sso.get("metadata_url")
        if not metadata_url:
            raise HTTPException(status_code=400, detail="SAML metadata_url is required before SSO can start")
        return {
            "provider": "saml",
            "status": "configured",
            "message": "SAML metadata is configured. Wire python-saml assertion handling before enabling redirects.",
            "metadata_url": metadata_url,
        }

    client_id = sso.get("client_id")
    authorize_url = sso.get("authorize_url")
    redirect_uri = sso.get("redirect_uri") or f"{frontend_url.rstrip('/')}/api/v1/auth/sso/callback"
    if not client_id or not authorize_url:
        raise HTTPException(status_code=400, detail="OIDC client_id and authorize_url are required before SSO can start")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": sso.get("scope") or "openid email profile",
        "state": state,
    }
    return {
        "provider": "oidc",
        "authorization_url": f"{authorize_url}?{urlencode(params)}",
        "state": state,
        "organization": {"id": str(org.id), "slug": org.slug, "name": org.name},
    }


def handle_sso_callback(db: Session, org_slug: str, code: str | None, state: str | None) -> dict:
    status = enterprise_sso_status(db, org_slug)
    if not status["enabled"]:
        raise HTTPException(status_code=400, detail="Enterprise SSO is not configured for this organization")
    if not code:
        raise HTTPException(status_code=400, detail="Missing SSO authorization code")
    return {
        "status": "pending_provider_exchange",
        "provider": status["provider"],
        "state": state,
        "message": "SSO configuration is present. Token exchange and assertion validation require provider secrets before production enablement.",
    }
