# Arceus Security Policy

## Supported Surfaces
Security fixes are prioritized for the current production branch and the latest desktop release.

## Reporting A Vulnerability
Do not open public issues for vulnerabilities. Email the security owner or use a private GitHub security advisory.

Include:
- affected product: Arceus Code, PA, Interview, Desktop, API, or infrastructure
- reproduction steps
- impact and data exposure risk
- affected commit, release, or environment

## Production Requirements
- Demo authentication must be disabled in production.
- `x-user-id` development fallback must be disabled in production.
- Provider keys must never be returned to the frontend.
- GitHub, Stripe, Clerk, LLM, storage, and encryption secrets must be stored only in managed environment secrets.
- Any destructive migration requires backup confirmation and release notes.

## Incident Handling
1. Triage severity and affected users.
2. Disable risky automations or agent jobs if needed.
3. Patch on a private branch.
4. Run CI, staging deploy, and smoke tests.
5. Deploy or roll back using `RELEASE.md`.
6. Record a post-incident note with root cause and prevention.
