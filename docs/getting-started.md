# Getting Started

## Install

Download the latest installer from GitHub Releases. Production builds are distributed as:

- Windows: NSIS installer
- macOS: DMG and PKG
- Linux: AppImage, deb, and rpm

Package-manager distribution is planned for:

- `winget install Arceus.Code`
- `brew install --cask arceus-code`

## First Project

1. Open Arceus Code.
2. Click **Open Folder**.
3. Select a project folder.
4. Open the bottom terminal and run a simple command such as `git status`.
5. Ask Arceus: `Explain this project and suggest the next 3 actions.`

Arceus keeps chats, terminals, patches, jobs, and files scoped to the active project.

## First Agent Run

Use the composer placeholder:

```text
Plan, Build, / for skills, @ for context
```

Arceus should return a work receipt that lists files inspected, changed files, commands/checks, approval state, and next actions.
