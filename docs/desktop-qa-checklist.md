# Arceus Code Desktop QA Checklist

Use this checklist after each desktop installer build or major workspace UI change. The goal is to prove the core loop works in the installed app, not only in the browser.

## 1. Start The Desktop Runtime

From the repo root:

```powershell
cd "C:\Users\amarn\OneDrive\Desktop\my ai\desktop"
npm start
```

Expected:

- Postgres and Redis are started or reused.
- `auth-service` reaches port `8001`.
- `goals-service` reaches port `8002`.
- `agent-service` reaches port `8003`.
- Frontend opens from the Electron window.

## 2. Run Strict Smoke Verification

In a second PowerShell window, set an admin smoke user and run:

```powershell
cd "C:\Users\amarn\OneDrive\Desktop\my ai"
$env:SMOKE_ADMIN_USER_ID="00000000-0000-0000-0000-000000000000"
.\scripts\full-verify.ps1 -StrictSmoke
```

Expected:

- Backend health and readiness: OK
- Production readiness endpoint: OK
- Admin release readiness gate: OK
- Admin billing gate: OK
- Admin observability gate: OK
- Admin rate-limit gate: OK
- Frontend route smoke: OK

If a smoke step fails, fix that first before testing product behavior.

## 3. Code-Only Desktop Shell

In the installed Electron window:

| Check | Expected result |
| --- | --- |
| Top-left logo | Shows `Arceus Code`. |
| Logo click | Opens `/workspace`; no product switcher appears. |
| Product Hub / PA / Interview / Admin | Not visible in Electron shell. |
| Login / Sign up | Not visible in Electron shell. |
| Account state | Shows `Connect account`, avatar, or `Connected`. |
| Service status | Shows `Online`, `Local mode`, `Agent offline`, or `Connect account` with a useful tooltip. |

## 4. Local Folder Trust

| Action | Expected result |
| --- | --- |
| Click `Open Folder` | Native folder picker opens. |
| Select a repo | Project opens without duplicate if already known. |
| Explorer drawer | Shows folder tree; `.git`, `node_modules`, `.next`, `dist`, `build` are hidden. |
| Edit file externally | Tree/editor updates within 1 second. |
| Unsaved edit | Dirty dot appears; disappears after save. |
| Create/rename/delete from UI | Operation stays inside trusted folder only. |

## 5. Bottom Terminal

| Action | Expected result |
| --- | --- |
| Open terminal icon | Bottom panel opens, not right drawer. |
| Check cwd | Cwd is selected trusted folder. |
| Run `dir` | Output appears quickly with no duplicate prompt. |
| Run `npm -v` | Version prints. |
| Run `git status` | Runs inside selected folder. |
| Kill/restart | Active process stops and terminal remains usable. |
| Close/reopen panel | Terminal state remains stable. |

## 6. Agent Work Receipt And Undo

Use a small safe prompt:

```text
create a file named arceus-smoke-test.txt with one line saying hello from Arceus
```

Expected:

- File appears without Apply/Discard for safe create/modify.
- Chat receipt shows changed files and line impact.
- Receipt shows `Undo changes`.
- Clicking `Undo changes` removes/restores the file and refreshes the tree.

## 7. Risky Change Review

Use a destructive prompt:

```text
delete arceus-smoke-test.txt
```

Expected:

- Delete is not auto-applied.
- Changes drawer shows review required.
- Accept/Reject/Apply selected controls are available only for pending risky changes.

## 8. Preview, Git, Jobs

| Surface | Expected result |
| --- | --- |
| Jobs | Compact rows show queued/running/failed/completed jobs; pause/cancel/retry states are clear. |
| Preview | Start/Re-verify/Fix buttons explain unavailable states when no preview URL exists. |
| Git | Connect GitHub appears when not connected; PR actions are disabled until repo/approved changes exist. |

## 9. Offline Recovery

Stop `agent-service` or disconnect backend temporarily.

Expected:

- Header shows `Local mode` or `Agent offline`.
- Local folder tree still works.
- Editor still opens/saves local files.
- Bottom local terminal still runs inside the trusted folder.
- Cloud agent/GitHub/preview/model cloud actions are disabled with clear tooltips.

## 10. Pass Criteria

The desktop build is QA-passed only when:

- `.\scripts\full-verify.ps1 -StrictSmoke` passes with no failures.
- Code-only shell is clean in Electron.
- Open folder, file tree, editor, and terminal work while online and offline.
- Safe agent file changes auto-apply and Undo works.
- Risky changes require review.
- Download/install flow launches the same Code-only shell.
