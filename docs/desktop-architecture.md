# Arceus Desktop Architecture

Book II Part 32 starts with concrete production guardrails in the current Electron app rather than a large directory migration.

## Implemented Foundations

- Secure BrowserWindow defaults: context isolation, no node integration, sandbox, web security, denied permission requests.
- Navigation policy: desktop windows stay on approved Arceus routes and external links go through the system browser.
- Pragmatic Content Security Policy for local Next.js development and hosted Arceus production.
- Structured desktop error and IPC response helpers.
- `window.arceusDesktop` namespace for typed capabilities:
  - `capabilities`
  - `diagnostics`
  - `workspace.openDirectory`
  - `workspace.setTrust`
  - `workspace.discoverTasks`
  - `filesystem.readFile`
  - `filesystem.writeFile`
  - `terminal.create`
  - `terminal.sendInput`
  - `terminal.kill`
  - `updater`
  - `system`
- Workspace identity and trust metadata.
- Stricter workspace path containment.
- Atomic file writes for local file save operations.
- Local task discovery for common `package.json`, Python, Make, Cargo, and Go projects.

## Compatibility

The legacy `window.electron` preload API remains available so existing workspace UI keeps working while new frontend code migrates to `window.arceusDesktop`.

## Remaining Desktop Work

1. Split `desktop/main.js` into `main/`, `ipc/`, `services/`, and `security/` modules.
2. Persist workspace trust and window/layout recovery snapshots to disk.
3. Add Git IPC service for status, diff, branch, commit, pull, push.
4. Add local model health checks for Ollama and OpenAI-compatible local servers.
5. Add command risk classifier and approval flow for agent-issued commands.
6. Move heavy indexing, search, diff, and Git work into utility processes.
7. Add crash recovery prompts for unsaved editor buffers.
8. Add desktop system tests for open folder, terminal, file write, recovery, and update checks.

