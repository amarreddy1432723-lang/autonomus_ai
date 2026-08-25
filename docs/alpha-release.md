# Arceus Code Alpha Release Checklist

This checklist is the release gate for the private Arceus Code Alpha. The goal is a small, honest build that early testers can install, sign into, open a repository, run a mission, review evidence, undo changes, and send useful diagnostics.

## Scope

Alpha includes:

- Windows desktop installer for Arceus Code.
- Desktop-only Code shell with local folder, editor, terminal, mission control, review, rollback, and diagnostics.
- Hosted control plane for auth, missions, verification, model routing, release metadata, and downloads.
- Private tester documentation, feedback capture, known issues, and support path.

Alpha does not claim:

- Public production launch readiness.
- Enterprise SSO completeness.
- Fully signed macOS/Linux distribution.
- Automatic resolution of every repository or build system.

## Required Commands

Run from the repository root:

```powershell
python -m compileall backend/services
python -m pytest backend -q
cd frontend
npm run build
cd ..\desktop
node --check main.js
node --check preload.js
cd ..
.\scripts\verify-alpha-release.ps1
```

Before a tagged release, also run:

```powershell
.\scripts\verify-desktop-release.ps1
.\scripts\verify-installed-product.ps1
.\scripts\full-verify.ps1
```

## Release Artifacts

Required for each Windows Alpha:

- `desktop/dist/Arceus Code-<version>-Setup.exe`
- SHA-256 checksum for the installer.
- GitHub Release containing the installer.
- Railway release/download environment variables:
  - `ARCEUS_RELEASE_VERSION`
  - `ARCEUS_RELEASE_NOTES_URL`
  - `ARCEUS_UPDATE_FEED_URL`
  - `ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL`
  - `ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256`

Unsigned builds may be used for private testing only. Public distribution requires a Windows signing certificate and a successful auto-update smoke test from the published GitHub Release.

## Alpha Smoke

Each release candidate must prove:

- Install and launch Arceus Code from Start Menu and desktop shortcut.
- Connect account with Clerk desktop auth.
- Restart the app and preserve the auth session.
- Sign out and confirm protected cloud actions lock again.
- Open an existing repository.
- File tree loads and ignored folders are hidden.
- Terminal opens in the trusted repository folder.
- Create a mission from a small repo task.
- Mission Control shows task progress, evidence, checks, and changes.
- Safe file changes apply with Undo available.
- Rollback restores files.
- Release gate blocks PR/deploy when checks fail.
- Export Diagnostics writes a redacted JSON bundle.

## Release Decision

Ship only when:

- No blockers remain in `.\scripts\verify-alpha-release.ps1`.
- Installer checksum matches the Railway download manifest.
- The installed app completes the alpha smoke on a clean Windows account.
- Known issues are current and visible to testers.
- Feedback and diagnostics instructions are included in the tester packet.
