# Arceus Code Core Loop Regression Checklist

Use this checklist after frontend, desktop, Electron bridge, terminal, or service startup changes.

## Automated Gate

Run:

```powershell
.\scripts\verify-core-loop.ps1 -StartDockerDeps
```

For CI-like failure behavior:

```powershell
.\scripts\verify-core-loop.ps1 -StartDockerDeps -Strict
```

The script writes:

```text
.verify/core-loop-summary.json
```

## Required Manual Checks

| Check | Pass condition |
| --- | --- |
| Open Folder | Native folder picker opens, selected folder appears in Explorer. |
| File Explorer | Ignored paths are hidden and real files appear in under 1 second for normal projects. |
| Open/Edit/Save file | Selecting a file loads content, edits mark dirty, Save writes to disk. |
| Dirty state indicator | Dirty marker appears after edit and disappears after save. |
| Terminal create/kill | Local terminal opens in trusted folder, command output appears, kill stops it. |
| Layout persistence | Sidebar, AI panel, and bottom panel sizes survive reload. |
| Download/install flow | `/download` shows a real installer when release envs are set. |
| Desktop launch | Installed app opens `/workspace` without product-suite clutter. |
| Workspace reload | Reloading keeps app usable and does not duplicate backend/frontend processes. |
| Offline mode | If agent API is down, local folder/editor/terminal remain usable. |
| Service reconnect | After backend starts, Retry services updates the AI panel state. |

## Current Blocking Dependency

The local desktop smoke requires one of these to be true:

- Docker Desktop engine is running, then `docker compose up -d postgres redis` succeeds.
- A local PostgreSQL instance is available and the desktop fallback can start it.
- `DATABASE_URL` and `REDIS_URL` point at reachable managed services.

Do not debug AI runtime behavior until the agent service returns a healthy `/api/v1/ready` response.
