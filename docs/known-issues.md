# Arceus Code Alpha Known Issues

This page must stay honest. Alpha testers should know what is expected to work and what is still being hardened.

## Current Limitations

- Windows is the primary Alpha platform. macOS and Linux release artifacts may be incomplete.
- Unsigned Windows builds can trigger SmartScreen warnings.
- Very large repositories may take longer to analyze on first open.
- Language support is strongest for JavaScript/TypeScript and Python projects.
- Some build systems need manual terminal setup before checks can run.
- Cloud agent actions require a valid desktop auth session.
- Local mode keeps file tree, editor, and terminal usable, but cloud missions, PR creation, billing, and model calls are disabled.
- Enterprise SSO, SCIM, and advanced device trust are not required for private Alpha.
- Auto-update requires the release repository and update feed to match the installed build metadata.

## Recovery Steps

- If the app does not open, restart Windows and launch from Start Menu.
- If auth is stuck, sign out, close the app, relaunch, and connect again.
- If services are offline, use **Retry services** and then **Open diagnostics**.
- If a mission appears stuck, pause it, restart the app, and verify Mission Control recovered the task state.
- If changes look wrong, use **Undo changes** before running more missions.
- If terminal output duplicates or freezes, kill the terminal tab and open a new one.

## Report Immediately

Report these as high priority:

- App launch crash.
- Auth session not persisted after restart.
- Any file written outside the selected workspace.
- Destructive change applied without review.
- Rollback failing to restore files.
- PR/deploy enabled when checks are failing.
- Logs exporting secrets or raw tokens.
