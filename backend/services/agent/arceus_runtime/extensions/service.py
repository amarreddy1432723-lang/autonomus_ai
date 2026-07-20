from __future__ import annotations

import hashlib
import json
import base64
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from .api_schemas import ExtensionPermission, ManifestValidationResponse, PermissionEvaluationResponse, PluginRuntimePolicyResponse, PluginSecretUseResponse


ARCEUS_PLUGIN_API_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "2026-07"
CORE_VERSION = "2.0.0"

SUPPORTED_EXTENSION_TYPES = {
    "tool",
    "model_provider",
    "agent_profile",
    "workflow_template",
    "repository_connector",
    "deployment_provider",
    "ui_extension",
    "data_connector",
    "verification_check",
    "policy_provider",
    "notification_provider",
    "authentication_provider",
    "billing_integration",
    "telemetry_exporter",
}

TYPE_ALIASES = {
    "connector": "data_connector",
    "ai_specialist": "agent_profile",
    "agent_specialist": "agent_profile",
    "agent_skill": "agent_profile",
    "panel": "ui_extension",
    "workflow_pack": "workflow_template",
    "event_consumer": "notification_provider",
    "verification_provider": "verification_check",
}

SUPPORTED_RUNTIMES = ["in_process", "isolated_process", "container", "wasm", "remote", "remote_http", "remote_mcp"]

SUPPORTED_PERMISSIONS = {
    "repository.read",
    "repository.write",
    "repository.execute_commands",
    "mission.read",
    "mission.create",
    "mission.update",
    "artifact.read",
    "artifact.write",
    "model.invoke",
    "tool.register",
    "secrets.use",
    "network.outbound",
    "network.unrestricted",
    "ui.sidebar.register",
    "ui.command.register",
    "events.subscribe",
    "notifications.send",
    "deployment.execute",
    "deployment.production",
    "verification.register",
    "telemetry.export",
    "plugin.health.read",
    "plugin.lifecycle.manage",
    "billing.write",
    "organization.admin",
    "policy.modify",
    "identity.manage",
    "artifact.export_sensitive",
}

PERMISSION_ALIASES = {
    "repositories.read": "repository.read",
    "repositories.write": "repository.write",
    "files:read": "repository.read",
    "files:write": "repository.write",
    "terminal:run": "repository.execute_commands",
    "agent:tool": "tool.register",
    "events.publish": "events.subscribe",
    "panel:render": "ui.sidebar.register",
}

HIGH_RISK_PERMISSIONS = {
    "repository.write",
    "repository.execute_commands",
    "secrets.use",
    "network.unrestricted",
    "deployment.execute",
    "deployment.production",
    "billing.write",
    "organization.admin",
    "policy.modify",
    "identity.manage",
    "artifact.export_sensitive",
}

TRUSTED_PUBLISHERS = {
    "arceus": "arceus",
    "arceus labs": "arceus",
    "openai": "trusted_partner",
    "anthropic": "trusted_partner",
    "google": "trusted_partner",
    "github": "trusted_partner",
    "gitlab": "trusted_partner",
    "atlassian": "trusted_partner",
    "linear": "trusted_partner",
    "slack": "trusted_partner",
    "railway": "trusted_partner",
    "vercel": "trusted_partner",
    "sentry": "trusted_partner",
    "prometheus": "trusted_partner",
    "groq": "trusted_partner",
}


OFFICIAL_MARKETPLACE = [
    {
        "plugin_key": "github.connector",
        "name": "GitHub Connector",
        "publisher": "GitHub",
        "category": "official",
        "version": "1.0.0",
        "description": "Repository, pull request, issue, and check-run integration.",
        "extension_types": ["data_connector", "tool"],
        "permissions": ["repository.read", "repository.write", "events.subscribe"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "gitlab.connector",
        "name": "GitLab Connector",
        "publisher": "Arceus",
        "category": "official",
        "version": "1.0.0",
        "description": "GitLab repository, merge request, and pipeline integration.",
        "extension_types": ["data_connector", "tool"],
        "permissions": ["repository.read", "repository.write", "events.subscribe"],
        "verification_level": "arceus",
    },
    {
        "plugin_key": "jira.connector",
        "name": "Jira Connector",
        "publisher": "Atlassian",
        "category": "official",
        "version": "1.0.0",
        "description": "Issues, projects, and engineering workflow integration for Jira.",
        "extension_types": ["data_connector", "workflow_template"],
        "permissions": ["mission.read", "mission.update", "events.subscribe"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "linear.connector",
        "name": "Linear Connector",
        "publisher": "Linear",
        "category": "official",
        "version": "1.0.0",
        "description": "Issues, projects, cycles, and mission handoff integration.",
        "extension_types": ["data_connector", "workflow_pack"],
        "permissions": ["mission.read", "mission.update", "events.subscribe"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "openai.model_provider",
        "name": "OpenAI Model Provider",
        "publisher": "OpenAI",
        "category": "official",
        "version": "1.0.0",
        "description": "Routes model calls to OpenAI models through governed provider credentials.",
        "extension_types": ["model_provider"],
        "permissions": ["model.invoke", "secrets.use"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "gemini.model_provider",
        "name": "Gemini Model Provider",
        "publisher": "Google",
        "category": "official",
        "version": "1.0.0",
        "description": "Routes governed multimodal model calls to Gemini models.",
        "extension_types": ["model_provider"],
        "permissions": ["model.invoke", "secrets.use"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "groq.model_provider",
        "name": "Groq Model Provider",
        "publisher": "Groq",
        "category": "official",
        "version": "1.0.0",
        "description": "Routes low-latency inference workloads to Groq-hosted models.",
        "extension_types": ["model_provider"],
        "permissions": ["model.invoke", "secrets.use"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "anthropic.model_provider",
        "name": "Anthropic Model Provider",
        "publisher": "Anthropic",
        "category": "official",
        "version": "1.0.0",
        "description": "Routes model calls to Anthropic models with policy and cost tracking.",
        "extension_types": ["model_provider"],
        "permissions": ["model.invoke", "secrets.use"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "ollama.local_provider",
        "name": "Ollama Local Provider",
        "publisher": "Arceus",
        "category": "official",
        "version": "1.0.0",
        "description": "Connects Arceus to local Ollama models for offline development.",
        "extension_types": ["model_provider"],
        "permissions": ["model.invoke"],
        "verification_level": "arceus",
    },
    {
        "plugin_key": "railway.deployment",
        "name": "Railway Deployment Provider",
        "publisher": "Railway",
        "category": "official",
        "version": "1.0.0",
        "description": "Deploys approved artifacts to Railway after release gates pass.",
        "extension_types": ["deployment_provider"],
        "permissions": ["deployment.execute", "secrets.use", "telemetry.export"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "slack.notifications",
        "name": "Slack Notifications",
        "publisher": "Slack",
        "category": "official",
        "version": "1.0.0",
        "description": "Sends governed mission, incident, and release notifications to Slack.",
        "extension_types": ["notification_provider"],
        "permissions": ["notifications.send", "events.subscribe"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "google_drive.connector",
        "name": "Google Drive Connector",
        "publisher": "Google",
        "category": "official",
        "version": "1.0.0",
        "description": "Connects requirements, design docs, and artifacts from Google Drive.",
        "extension_types": ["data_connector"],
        "permissions": ["artifact.read", "artifact.write", "secrets.use"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "vercel.deployment",
        "name": "Vercel Deployment Provider",
        "publisher": "Vercel",
        "category": "official",
        "version": "1.0.0",
        "description": "Deploys approved frontend artifacts to Vercel preview and production.",
        "extension_types": ["deployment_provider"],
        "permissions": ["deployment.execute", "secrets.use", "telemetry.export"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "sentry.observability",
        "name": "Sentry Integration",
        "publisher": "Sentry",
        "category": "official",
        "version": "1.0.0",
        "description": "Imports issues, releases, traces, and deployment health.",
        "extension_types": ["data_connector", "notification_provider"],
        "permissions": ["telemetry.export", "events.subscribe"],
        "verification_level": "trusted_partner",
    },
    {
        "plugin_key": "prometheus.exporter",
        "name": "Prometheus Exporter",
        "publisher": "Prometheus",
        "category": "official",
        "version": "1.0.0",
        "description": "Exports runtime and mission metrics for operational dashboards.",
        "extension_types": ["telemetry_exporter", "verification_check"],
        "permissions": ["telemetry.export", "verification.register"],
        "verification_level": "trusted_partner",
    },
]


def stable_json_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def payload_fingerprint(value: dict[str, Any]) -> str:
    return stable_json_digest(_redact_sensitive(value))


def publisher_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower()).strip("-") or "unknown"


def extension_identity(plugin_key: str, scope_type: str, scope_id: str) -> str:
    digest = hashlib.sha256(f"{plugin_key}:{scope_type}:{scope_id}".encode("utf-8")).hexdigest()[:16]
    return f"ext_{digest}"


def normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    root = raw.get("plugin") if isinstance(raw.get("plugin"), dict) else raw
    plugin_key_value = root.get("id") or root.get("plugin_id") or raw.get("id")
    name = root.get("name") or raw.get("name")
    version = root.get("version") or raw.get("version")
    publisher_raw = root.get("publisher") or root.get("author") or raw.get("publisher") or raw.get("author") or "unknown"
    if isinstance(publisher_raw, dict):
        publisher_name = publisher_raw.get("name") or publisher_raw.get("id") or "unknown"
    else:
        publisher_name = str(publisher_raw)
    extension_types_raw = root.get("extensionTypes") or root.get("extension_types") or root.get("types") or raw.get("extensionTypes") or raw.get("type") or ["tool"]
    if isinstance(extension_types_raw, str):
        extension_types_raw = [extension_types_raw]
    permissions_raw = root.get("permissions") or raw.get("permissions") or []
    runtime = root.get("runtime") or raw.get("runtime") or {}
    integrity = root.get("integrity") or raw.get("integrity") or {}
    signature = root.get("signature") or raw.get("signature") or integrity.get("signature")
    signing_public_key = integrity.get("publicKey") or integrity.get("public_key") or root.get("signingPublicKey")
    certificate_pem = integrity.get("certificate") or root.get("certificate")
    package_digest = integrity.get("packageDigest") or integrity.get("package_digest") or raw.get("package_digest")
    normalized_permissions: list[dict[str, Any]] = []
    for item in permissions_raw:
        if isinstance(item, str):
            permission = item
            reason = None
            scope: dict[str, Any] = {}
        else:
            permission = item.get("permission") or item.get("key") or item.get("name")
            reason = item.get("reason")
            scope = item.get("scope") or {}
        permission = PERMISSION_ALIASES.get(str(permission), str(permission))
        normalized_permissions.append(
            {
                "permission": permission,
                "risk_level": "high" if permission in HIGH_RISK_PERMISSIONS else "low",
                "scope": scope,
                "conditions": item.get("conditions", {}) if isinstance(item, dict) else {},
                "reason": reason,
            }
        )
    extension_types = [TYPE_ALIASES.get(str(item), str(item)) for item in extension_types_raw]
    return {
        "id": plugin_key_value,
        "name": name,
        "version": version,
        "publisher": {"key": publisher_key(publisher_name), "name": publisher_name},
        "description": root.get("description") or raw.get("description") or "",
        "extension_types": extension_types,
        "permissions": normalized_permissions,
        "runtime": runtime,
        "integrity": {
            "signature": signature,
            "package_digest": package_digest,
            "public_key": signing_public_key,
            "certificate": certificate_pem,
            "signed_payload": integrity.get("signedPayload") or integrity.get("signed_payload") or root.get("signedPayload"),
        },
        "capabilities": root.get("capabilities") or raw.get("capabilities") or [],
        "compatibility": root.get("compatibility") or raw.get("compatibility") or {},
        "data_disclosure": root.get("dataDisclosure") or root.get("data_disclosure") or raw.get("dataDisclosure") or {},
        "raw": raw,
    }


def validate_plugin_manifest(raw: dict[str, Any], package_digest: str | None = None) -> ManifestValidationResponse:
    normalized = normalize_manifest(raw)
    errors: list[str] = []
    warnings: list[str] = []

    plugin_key_value = normalized.get("id")
    name = normalized.get("name")
    version = normalized.get("version")
    if not plugin_key_value:
        errors.append("Plugin id is required.")
    if not name:
        errors.append("Plugin name is required.")
    if not version or not re.match(r"^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$", str(version)):
        errors.append("Plugin version must be semantic, for example 1.0.0.")

    extension_types = normalized["extension_types"]
    unknown_types = sorted(set(extension_types) - SUPPORTED_EXTENSION_TYPES)
    if unknown_types:
        errors.append(f"Unsupported extension type(s): {', '.join(unknown_types)}.")

    permissions = [ExtensionPermission(**item) for item in normalized["permissions"]]
    unknown_permissions = sorted({item.permission for item in permissions} - SUPPORTED_PERMISSIONS)
    if unknown_permissions:
        errors.append(f"Unsupported permission(s): {', '.join(unknown_permissions)}.")

    runtime = normalized.get("runtime") or {}
    min_core = runtime.get("minCoreVersion") or runtime.get("min_core_version") or runtime.get("min_version") or "1.0.0"
    if _major(str(min_core)) > _major(CORE_VERSION):
        errors.append(f"Plugin requires Arceus Core {min_core}, but this runtime is {CORE_VERSION}.")
    runtime_kind = runtime.get("type") or runtime.get("kind") or "remote_http"
    if runtime_kind not in SUPPORTED_RUNTIMES:
        errors.append(f"Unsupported runtime '{runtime_kind}'.")

    signature = normalized["integrity"].get("signature")
    effective_package_digest = package_digest or normalized["integrity"].get("package_digest")
    signature_check = verify_manifest_signature(normalized)
    certificate_check = verify_manifest_certificate(normalized["integrity"].get("certificate"))
    signed = signature_check["valid"] or bool(signature and str(signature).startswith("sha256:"))
    if not signed:
        warnings.append(signature_check["reason"] or "Plugin is unsigned and cannot be enabled without review.")
    if certificate_check["present"] and not certificate_check["valid"]:
        errors.append(certificate_check["reason"])
    if effective_package_digest and not re.match(r"^(sha256:)?[0-9a-fA-F]{64}$", str(effective_package_digest)):
        errors.append("Package digest must be a SHA-256 digest.")

    high_risk = [item.permission for item in permissions if item.permission in HIGH_RISK_PERMISSIONS]
    if high_risk:
        warnings.append(f"High-risk permission review required: {', '.join(high_risk)}.")

    verification_level = TRUSTED_PUBLISHERS.get(normalized["publisher"]["key"]) or TRUSTED_PUBLISHERS.get(normalized["publisher"]["name"].lower(), "unverified")
    verified = signed and certificate_check["valid"] is not False and verification_level in {"trusted_partner", "arceus"}
    security_score = _security_score(signed=signed, verified=verified, high_risk_count=len(high_risk), unknown_count=len(unknown_permissions) + len(unknown_types))
    review_required = bool(high_risk or not signed or not verified)

    normalized["integrity"]["package_digest"] = effective_package_digest
    normalized["integrity"]["signature_check"] = signature_check
    normalized["integrity"]["certificate_check"] = certificate_check
    return ManifestValidationResponse(
        valid=not errors,
        plugin_key=plugin_key_value,
        name=name,
        version=version,
        publisher_key=normalized["publisher"]["key"],
        extension_types=extension_types,
        permissions=permissions,
        signed=signed,
        verified=verified,
        security_score=security_score,
        review_required=review_required,
        manifest_digest=stable_json_digest(normalized["raw"]),
        errors=errors,
        warnings=warnings,
        normalized_manifest=normalized,
    )


def evaluate_permission_grants(
    *,
    installation_status: str,
    granted_permissions: list[dict[str, Any]],
    requested_permission: str,
    risk_level: str,
    scope: dict[str, Any] | None = None,
) -> PermissionEvaluationResponse:
    if installation_status not in {"enabled", "installed"}:
        return PermissionEvaluationResponse(
            allowed=False,
            decision="deny",
            reason=f"Extension installation is {installation_status}.",
            obligations=["enable_extension"],
        )
    requested = PERMISSION_ALIASES.get(requested_permission, requested_permission)
    active_grants = [grant for grant in granted_permissions if not grant.get("revoked_at")]
    matching = [grant for grant in active_grants if grant.get("permission") == requested or grant.get("permission_key") == requested]
    if not matching:
        return PermissionEvaluationResponse(
            allowed=False,
            decision="deny",
            reason="Permission was not granted during installation.",
            obligations=["request_permission_approval"],
        )
    if requested in HIGH_RISK_PERMISSIONS or risk_level in {"high", "critical"}:
        return PermissionEvaluationResponse(
            allowed=False,
            decision="needs_review",
            reason="High-risk extension action requires explicit review.",
            matched_permissions=[requested],
            obligations=["record_audit_event", "request_human_approval"],
        )
    if scope and any(_scope_conflict(grant.get("scope") or {}, scope) for grant in matching):
        return PermissionEvaluationResponse(
            allowed=False,
            decision="deny",
            reason="Requested resource is outside the granted extension scope.",
            matched_permissions=[requested],
            obligations=["narrow_scope_or_reapprove"],
        )
    return PermissionEvaluationResponse(
        allowed=True,
        decision="allow",
        reason="Permission is granted and low risk.",
        matched_permissions=[requested],
        obligations=["record_audit_event", "meter_usage"],
    )


def runtime_policy_for_manifest(manifest: dict[str, Any], *, installation_id: UUID) -> PluginRuntimePolicyResponse:
    runtime = manifest.get("runtime") or {}
    runtime_type = runtime.get("type") or runtime.get("kind") or "remote"
    permissions = {item.get("permission") for item in manifest.get("permissions", []) if isinstance(item, dict)}
    domains = []
    for item in manifest.get("permissions", []):
        if isinstance(item, dict):
            domains.extend((item.get("scope") or {}).get("domains") or [])
    if runtime_type == "in_process":
        isolation = "process"
        allow_subprocesses = False
    elif runtime_type == "container":
        isolation = "container"
        allow_subprocesses = False
    elif runtime_type == "wasm":
        isolation = "wasm"
        allow_subprocesses = False
    else:
        isolation = "remote"
        allow_subprocesses = False
    allow_network = "network.outbound" in permissions or "network.unrestricted" in permissions or runtime_type in {"remote", "remote_http", "remote_mcp"}
    return PluginRuntimePolicyResponse(
        installation_id=installation_id,
        runtime_type=runtime_type,
        minimum_isolation=isolation,
        allow_network=allow_network,
        allowed_domains=[] if "network.unrestricted" in permissions else sorted(set(domains)),
        filesystem_mode="workspace_overlay" if "repository.write" in permissions else "read_only" if "repository.read" in permissions else "none",
        maximum_cpu_millis=int(runtime.get("maximumCpuMillis") or runtime.get("maximum_cpu_millis") or 30_000),
        maximum_memory_mb=int(runtime.get("maximumMemoryMb") or runtime.get("maximum_memory_mb") or 512),
        maximum_execution_seconds=int(runtime.get("maximumExecutionSeconds") or runtime.get("maximum_execution_seconds") or 60),
        allow_subprocesses=allow_subprocesses,
    )


def broker_secret_use(
    *,
    installation_status: str,
    granted_permissions: list[dict[str, Any]],
    secret_references: list[str],
    secret_ref: str,
    purpose: str,
    target_domain: str | None = None,
) -> PluginSecretUseResponse:
    decision = evaluate_permission_grants(
        installation_status=installation_status,
        granted_permissions=granted_permissions,
        requested_permission="secrets.use",
        risk_level="high",
        scope={"domains": [target_domain] if target_domain else []},
    )
    receipt_id = "secret_broker_" + stable_json_digest({"secret_ref": secret_ref, "purpose": purpose, "target_domain": target_domain})[:16]
    if secret_ref not in secret_references:
        return PluginSecretUseResponse(
            allowed=False,
            broker_receipt_id=receipt_id,
            secret_ref=secret_ref,
            secret_fingerprint=None,
            expires_in_seconds=0,
            reason="Secret reference is not bound to this installation.",
            obligations=["bind_secret_reference"],
        )
    if decision.decision == "deny":
        return PluginSecretUseResponse(
            allowed=False,
            broker_receipt_id=receipt_id,
            secret_ref=secret_ref,
            secret_fingerprint=hashlib.sha256(secret_ref.encode("utf-8")).hexdigest()[:16],
            expires_in_seconds=0,
            reason=decision.reason,
            obligations=decision.obligations,
        )
    return PluginSecretUseResponse(
        allowed=decision.decision == "allow",
        broker_receipt_id=receipt_id,
        secret_ref=secret_ref,
        secret_fingerprint=hashlib.sha256(secret_ref.encode("utf-8")).hexdigest()[:16],
        expires_in_seconds=300 if decision.decision == "allow" else 0,
        direct_value_returned=False,
        reason="Secret use authorized through broker receipt." if decision.decision == "allow" else "Secret use requires human approval before broker execution.",
        obligations=decision.obligations,
    )


def sdk_manifest() -> dict[str, Any]:
    return {
        "api_version": ARCEUS_PLUGIN_API_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "supported_extension_types": sorted(SUPPORTED_EXTENSION_TYPES),
        "supported_permissions": sorted(SUPPORTED_PERMISSIONS),
        "runtimes": SUPPORTED_RUNTIMES,
        "lifecycle_hooks": ["install", "configure", "enable", "disable", "update", "remove", "health_check"],
        "security": {
            "default_deny": True,
            "signature_required_for_enable": True,
            "high_risk_requires_review": True,
            "secrets_are_brokered": True,
            "runtime_execution": "disabled_until_policy_allows",
        },
    }


def invocation_receipt(*, capability_id: str, permission: str, dry_run: bool, allowed: bool, reason: str) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "permission": permission,
        "dry_run": dry_run,
        "allowed": allowed,
        "reason": reason,
        "runtime_executed": False,
        "note": "Extension code execution is intentionally gated behind the tool runtime policy layer.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_manifest_signature(normalized: dict[str, Any]) -> dict[str, Any]:
    integrity = normalized.get("integrity") or {}
    signature = integrity.get("signature")
    public_key = integrity.get("public_key")
    if not signature:
        return {"valid": False, "present": False, "reason": "Plugin manifest has no signature."}
    if not public_key:
        return {"valid": False, "present": True, "reason": "Plugin signature is present but no public key was supplied for verification."}
    signed_payload = integrity.get("signed_payload") or normalized.get("manifest_digest") or stable_json_digest(normalized.get("raw") or {})
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519, padding
    except Exception:
        return {"valid": False, "present": True, "reason": "cryptography package is unavailable for signature verification."}
    try:
        public_key_bytes = _decode_armored(public_key)
        signature_bytes = _decode_signature(str(signature))
        loaded = serialization.load_pem_public_key(public_key_bytes)
        payload_bytes = str(signed_payload).encode("utf-8")
        if isinstance(loaded, ed25519.Ed25519PublicKey):
            loaded.verify(signature_bytes, payload_bytes)
        else:
            loaded.verify(signature_bytes, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        return {"valid": True, "present": True, "reason": "Signature verified."}
    except Exception as exc:
        return {"valid": False, "present": True, "reason": f"Signature verification failed: {exc}"}


def verify_manifest_certificate(certificate_pem: str | None) -> dict[str, Any]:
    if not certificate_pem:
        return {"valid": None, "present": False, "reason": "No certificate supplied."}
    try:
        from cryptography import x509
    except Exception:
        return {"valid": False, "present": True, "reason": "cryptography package is unavailable for certificate parsing."}
    try:
        cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
        now = datetime.now(timezone.utc)
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
        if now < not_before or now > not_after:
            return {"valid": False, "present": True, "reason": "Signing certificate is expired or not yet valid."}
        return {
            "valid": True,
            "present": True,
            "reason": "Certificate parsed and validity period is current.",
            "subject": cert.subject.rfc4514_string(),
            "not_after": not_after.isoformat(),
        }
    except Exception as exc:
        return {"valid": False, "present": True, "reason": f"Certificate parsing failed: {exc}"}


def _decode_signature(value: str) -> bytes:
    cleaned = value
    for prefix in ("sig:", "base64:", "sha256:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    try:
        return base64.b64decode(cleaned, validate=True)
    except Exception:
        return bytes.fromhex(cleaned)


def _decode_armored(value: str) -> bytes:
    if "BEGIN PUBLIC KEY" in value:
        return value.encode("utf-8")
    return base64.b64decode(value)


def _major(version: str) -> int:
    try:
        return int(version.split(".", 1)[0])
    except (TypeError, ValueError):
        return 999


def _security_score(*, signed: bool, verified: bool, high_risk_count: int, unknown_count: int) -> float:
    score = 50.0
    if signed:
        score += 20.0
    if verified:
        score += 20.0
    score -= min(high_risk_count * 6.0, 24.0)
    score -= min(unknown_count * 15.0, 30.0)
    return max(0.0, min(100.0, round(score, 2)))


def _scope_conflict(grant_scope: dict[str, Any], requested_scope: dict[str, Any]) -> bool:
    for key, granted_value in grant_scope.items():
        requested_value = requested_scope.get(key)
        if requested_value is None:
            continue
        if isinstance(granted_value, list):
            if requested_value not in granted_value and "*" not in granted_value:
                return True
        elif granted_value not in {requested_value, "*"}:
            return True
    return False


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(token in key.lower() for token in ("secret", "token", "password", "key")) else _redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
