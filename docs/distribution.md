# Distribution

## Release Channels

Primary channel: GitHub Releases.

Planned package managers:

- Windows Package Manager: `winget install Arceus.Code`
- Homebrew Cask: `brew install --cask arceus-code`

Before tagging a release, run:

```powershell
.\scripts\verify-desktop-release.ps1
```

For the final public package-manager submission, run the same check with strict external artifact validation after replacing the winget SHA:

```powershell
.\scripts\verify-desktop-release.ps1 -StrictExternal
```

## Signing

Windows:

- NSIS installer
- EV certificate recommended
- Configure `WINDOWS_CERTIFICATE_SUBJECT_NAME`
- Configure `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD` in GitHub Actions secrets.

macOS:

- Apple Developer ID
- Hardened runtime
- Notarization
- Configure `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID` in GitHub Actions secrets.

Linux:

- AppImage
- deb
- rpm

## Auto Update

Electron auto-update uses GitHub Releases through `electron-updater`. Production builds check for updates on startup and prompt to restart after download.

The desktop preload exposes update status through:

- `window.electron.onUpdateStatus`
- `window.electron.onUpdateAvailable`
- `window.electron.onUpdateReady`
- `window.electron.installUpdate`

The release workflow publishes Electron artifacts on `arceus-code-v*` tags and generates release download environment values from the built artifacts.
