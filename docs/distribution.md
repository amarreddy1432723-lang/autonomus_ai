# Distribution

## Release Channels

Primary channel: GitHub Releases.

Planned package managers:

- Windows Package Manager: `winget install Arceus.Code`
- Homebrew Cask: `brew install --cask arceus-code`

## Signing

Windows:

- NSIS installer
- EV certificate recommended
- Configure `WINDOWS_CERTIFICATE_SUBJECT_NAME`

macOS:

- Apple Developer ID
- Hardened runtime
- Notarization

Linux:

- AppImage
- deb
- rpm

## Auto Update

Electron auto-update uses GitHub Releases through `electron-updater`. Production builds check for updates on startup and prompt to restart after download.
