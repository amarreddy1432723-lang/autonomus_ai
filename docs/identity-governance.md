# Arceus Identity Governance

Book II Part 44 adds the identity, authorization, and enterprise governance facade for the Arceus runtime.

## API Surface

- `GET /api/v1/identity/me`
- `GET /api/v1/identity/roles`
- `GET /api/v1/identity/policies`
- `POST /api/v1/identity/authorize`
- `POST /api/v1/identity/sessions/risk`
- `POST /api/v1/identity/tokens/issue`
- `POST /api/v1/identity/service-accounts`
- `POST /api/v1/identity/agents`
- `GET /api/v1/identity/governance-summary`
- `POST /api/v1/identity/providers/sync-clerk`

## What It Provides

- Built-in roles for owners, administrators, developers, reviewers, security, QA, production operators, AI operators, and viewers.
- Default-deny authorization decisions with explicit matched policies, obligations, effective permissions, and audit event shape.
- Tenant isolation checks across organization boundaries.
- MFA and re-authentication obligations for high-risk and production actions.
- Separation-of-duties checks for critical approvals.
- AI identity restrictions so agents cannot count as human approval, access production secrets, merge protected branches, or change identity policy.
- Session risk scoring for untrusted devices, missing MFA, failed logins, idle sessions, and impossible travel.
- Scoped API token issue responses with checksums and one-time token previews only.
- Service account and agent identity creation responses with short-lived credential policies.
- Persistence tables for sessions, API token checksums, service accounts, agent identities, authorization decisions, identity providers, and role permissions.
- Role-derived request permissions. Local development still bootstraps an `owner`, but runtime authorization no longer depends on unconditional all-permission grants.
- Clerk organization/session/device trust metadata capture through request headers and identity provider sync.

## Relationship To Clerk

Clerk remains the MVP identity provider for login, MFA, OAuth, and session lifecycle. This module owns Arceus-side authorization, agent/service identities, governance decisions, and audit-ready explanations.

## Persistence

The migration `j7e8f9a0b1c2_arceus_identity_governance.py` creates:

- `arceus_role_permissions`
- `arceus_user_sessions`
- `arceus_api_tokens`
- `arceus_service_accounts`
- `arceus_agent_identities`
- `arceus_authorization_decisions`
- `arceus_identity_providers`

API tokens persist only `prefix`, `checksum_sha256`, scopes, expiration, and metadata. Full token material is not stored.

## Remaining External Setup

- Configure Clerk production organizations, enterprise SSO, SCIM, and MFA policies in Clerk.
- Send Clerk org/session/device-trust claims to the backend from the desktop/web clients.
- Connect a real secret vault for token issuing and rotation. The backend schema and API now enforce checksum-only storage, but vault brokerage depends on deployed infrastructure.
