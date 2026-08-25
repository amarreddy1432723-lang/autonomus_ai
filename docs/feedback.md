# Arceus Code Feedback and Diagnostics

Alpha feedback should help reproduce and fix problems quickly while protecting tester data.

## What To Send

- Short title.
- Expected behavior.
- Actual behavior.
- Steps to reproduce.
- App version.
- Windows version.
- Repository language/framework.
- Screenshot or screen recording when useful.
- Exported diagnostics JSON for technical failures.

## What Not To Send

- API keys.
- Access tokens.
- Passwords.
- Customer data.
- Private source files unless explicitly requested and approved.
- Production secrets.

## Diagnostics Contents

The desktop diagnostics export includes:

- App version and platform.
- Electron/Node/Chrome versions.
- Hosted control plane origin.
- Backend and frontend process state.
- Terminal session counts.
- Trusted workspace count.
- Redacted desktop logs.
- Crash marker JSON files.

The export intentionally excludes the encrypted desktop auth session and does not include repository source code.

## Triage Labels

- `alpha-launch`: install or open failure.
- `alpha-auth`: sign-in, sign-out, or token persistence.
- `alpha-local`: folder, tree, editor, or terminal.
- `alpha-mission`: mission runtime, worker, or recovery.
- `alpha-review`: patch review, safe apply, rollback, or release gate.
- `alpha-cloud`: Railway, Clerk, model provider, Redis, or database.
- `alpha-ui`: visual, layout, copy, or interaction issue.
