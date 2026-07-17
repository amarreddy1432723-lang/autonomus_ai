# Arceus Code UI Preview Pack

This pack is the approval target for the installed **Arceus Code** desktop experience. It is intentionally Code-only: no Product Hub, PA, Interview, Admin, public Login, or public Sign up controls should appear inside Electron.

Use this with:

- `frontend/src/app/ui-preview/arceus-code/page.tsx`
- `docs/ui-previews/button-state-audit.md`

## Review Rules

| Rule | Expected behavior |
| --- | --- |
| Code-only shell | Logo opens `/workspace`; Electron blocks suite routes. |
| Local-first failure mode | Folder tree, editor, and terminal remain usable when API is offline. |
| Bottom terminal | Terminal opens from the bottom, never as the right drawer. |
| Right rail | Explorer, Changes, Jobs, Preview, Git, Apps, Tasks are icon-first drawers. |
| Auto-apply trust | Safe create/modify/folder edits show `Undo changes`, not mandatory Apply/Discard. |
| Risk controls | Delete, rename, conflict, stale hash, install, command execution, and PR require review/confirmation. |

## 01. Desktop Shell - Signed Out

![Desktop Shell - Signed Out](./01-desktop-shell-signed-out.png)

Purpose: Code-only shell before desktop auth.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Sidebar toggle | Collapse/expand Code sidebar. | Always available. | Frontend state |
| 2 | Arceus Code logo | Opens `/workspace`. Never opens product switcher. | Always available. | Desktop route guard |
| 3 | Command search | Opens command/search palette. | Local commands still available offline. | Frontend state |
| 4 | Service status | Retries service health. | Shows `Agent offline`, `Local mode`, or `Connect account`. | `/api/v1/ready` |
| 5 | Connect account | Opens desktop auth handoff. | Shows re-auth state if token expired. | Clerk desktop auth |
| 6 | Notifications | Opens Code-only issues/approvals. | Badge only for Code events. | Frontend state |

## 02. Desktop Shell - Signed In

![Desktop Shell - Signed In](./02-desktop-shell-signed-in.png)

Purpose: Signed-in desktop shell with avatar replacing public auth CTAs.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Workspace logo | Opens `/workspace`. | Always available. | Desktop route guard |
| 2 | Search palette | Opens command/search. | Search remains local when API offline. | Frontend state |
| 3 | Online status | Refreshes readiness. | Shows partial/offline state. | Backend health |
| 4 | Avatar menu | Opens account menu. | Shows `Re-authenticate` if token expired. | Clerk session |
| 5 | Notifications | Opens Code notifications. | No suite-wide notifications. | Frontend state |
| 6 | Settings | Opens Code desktop settings. | Suite settings hidden in Electron. | Desktop shell mode |

## 03. API Offline - Local Mode

![API Offline - Local Mode](./03-api-offline-local-mode.png)

Purpose: API offline recovery while local work remains usable.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Retry services | Rechecks backend readiness. | Shows exact failing service. | `/api/v1/ready` |
| 2 | Connect account | Starts auth handoff. | Disabled only if auth route unavailable. | Clerk |
| 3 | Open folder | Opens native folder picker. | Local-only still allowed. | Electron IPC |
| 4 | Use local terminal | Opens bottom PTY terminal. | Requires trusted folder. | Electron PTY |
| 5 | Open diagnostics | Opens service diagnostics. | Shows local logs where possible. | Frontend + backend health |
| 6 | Cloud agent | Disabled while agent API offline. | Tooltip explains local-only mode. | Agent service |

## 04. Workspace Empty

![Workspace Empty](./04-workspace-empty.png)

Purpose: First launch workspace with one obvious next step.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Open Folder | Create/reopen trusted project. | Disabled while picker is busy. | Electron IPC |
| 2 | New Chat | Creates project-scoped chat. | Disabled until project/backend available. | Active project |
| 3 | Search | Opens workspace search. | Empty state if no folder. | Frontend state |
| 4 | Explorer | Opens right file tree drawer. | Shows open-folder prompt if no project. | Local project |
| 5 | Toggle Editor | Shows/hides Monaco editor. | Always available. | Frontend state |
| 6 | Send prompt | Creates task/chat message. | Cloud run disabled offline; local plan still allowed. | Auth + agent |

## 05. Open Folder + File Tree

![Open Folder + File Tree](./05-open-folder-file-tree.png)

Purpose: Right Explorer drawer as source-of-truth folder view.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Open Folder | Reopen/select another folder. | Max 3 projects prompts replacement. | Electron IPC |
| 2 | File row | Opens file in editor. | Large/generated files open read-only. | File IPC |
| 3 | New file | Creates file at selected path. | Blocks outside workspace. | Trusted folder |
| 4 | New folder | Creates folder recursively. | Blocks outside workspace. | Trusted folder |
| 5 | Refresh tree | Rescans folder tree. | Watch errors show retry. | Chokidar/Electron |
| 6 | Close drawer | Hides Explorer drawer. | Always available. | Frontend state |

## 06. Editor + Chat + Bottom Terminal

![Editor + Chat + Bottom Terminal](./06-editor-chat-terminal.png)

Purpose: Daily Code loop: editor, chat, and bottom terminal.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Editor tab | Switches active file. | Dirty dot marks unsaved edits. | Monaco |
| 2 | Ask composer | Sends prompt / creates task. | Cloud execution disabled offline. | Agent service |
| 3 | Terminal tab | Switches terminal session. | Shows killed/offline state. | PTY session |
| 4 | Run command | Sends stdin to terminal. | Restricted to trusted folder. | Electron PTY |
| 5 | Copy terminal | Copies output/selection. | Disabled if no output. | Clipboard |
| 6 | Kill terminal | Kills active process. | Disabled when idle/no process. | PTY session |

## 07. Auto-Applied Work Receipt

![Auto-Applied Work Receipt](./07-agent-work-receipt-auto-applied.png)

Purpose: Safe changes apply immediately and show rollback proof.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Undo changes | Restores latest rollback snapshot. | Hidden when no snapshot. | Rollback API |
| 2 | Open changed file | Opens changed file tab. | Disabled if file missing. | File tree/editor |
| 3 | Run checks | Runs project checks. | Disabled offline unless local runner exists. | Worker/sandbox/local |
| 4 | Create PR | Opens Git flow for applied changes. | Disabled until GitHub connected. | GitHub App |
| 5 | View details | Expands raw assistant/details. | Always available. | Frontend state |
| 6 | Type next action | Inserts suggested action into composer. | Never auto-runs blindly. | Suggest-next flow |

## 08. Risky Change Review Required

![Risky Change Review Required](./08-risky-change-review-required.png)

Purpose: Destructive/stale/conflicted changes are held for review.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Accept hunk | Marks hunk accepted. | Disabled when conflict blocks apply. | Patch review state |
| 2 | Reject hunk | Marks hunk rejected. | Disabled when no hunk selected. | Patch review state |
| 3 | Apply selected | Applies accepted hunks only. | Disabled if all rejected/stale. | Patch apply API |
| 4 | Reset review | Clears review choices. | Disabled without pending patch. | Patch review state |
| 5 | Undo safe changes | Rolls back auto-applied safe subset. | Hidden without snapshot. | Rollback API |
| 6 | Close Changes | Hides drawer. | Always available. | Frontend state |

## 09. Jobs Drawer

![Jobs Drawer](./09-jobs-drawer.png)

Purpose: Durable background jobs in compact rows.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Pause job | Pauses/revokes running job. | Hidden unless running. | Worker queue |
| 2 | Resume job | Requeues paused job. | Hidden unless paused. | Durable job record |
| 3 | Cancel job | Cancels queued/running job. | Hidden after completion. | Worker queue |
| 4 | Retry job | Requeues failed/dead-letter job. | Hidden unless retryable. | Job payload |
| 5 | View logs | Opens logs/artifacts. | Empty state when no logs. | Durable logs |
| 6 | Refresh jobs | Reloads job status. | Shows worker disabled/offline. | Jobs API |

## 10. Preview Verification

![Preview Verification](./10-preview-verification.png)

Purpose: Runtime preview proof with screenshot and evidence.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Start preview | Starts dev server/runtime. | Disabled without project/runtime. | Sandbox/runtime |
| 2 | Re-verify | Runs Playwright verification. | Disabled without preview URL. | Preview verifier |
| 3 | Fix preview issue | Sends console/network/blank evidence to agent. | Disabled without evidence. | Agent + patch flow |
| 4 | Open external | Opens preview URL externally. | Disabled without URL. | Preview URL |
| 5 | Screenshot | Expands captured screenshot. | Empty until verification runs. | Preview artifact |
| 6 | Console row | Expands console/network detail. | Empty if no errors. | Verification report |

## 11. Git PR Flow

![Git PR Flow](./11-git-pr-flow.png)

Purpose: GitHub App flow from approved changes to PR checks.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Connect GitHub | Starts GitHub App install. | Reconnect prompt if app uninstalled. | GitHub App |
| 2 | Repo picker | Selects installation repo. | Disabled until connected. | Installation token |
| 3 | Create branch | Creates branch from base. | Validates branch name. | GitHub API |
| 4 | Commit approved changes | Commits approved hunks only. | Blocks stale/conflicted patches. | Patch review state |
| 5 | Open PR | Creates PR. | Disabled until branch/commit ready. | GitHub API |
| 6 | Refresh checks | Polls CI check runs. | Disabled until PR exists. | GitHub Checks API |

## 12. Settings - Arceus Code

![Settings - Arceus Code](./12-settings-code.png)

Purpose: Desktop Code settings only.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Open workspace | Navigates to `/workspace`. | Always available. | Desktop route guard |
| 2 | Refresh projects | Reloads project/local service status. | Shows auth/API message. | Agent API |
| 3 | Project open | Opens selected project. | Disabled if folder missing. | Project metadata |
| 4 | Project close | Removes from open list only. | Never deletes disk folder. | Local state |
| 5 | Project remove | Archives project from app. | Confirmation required. | Projects API |
| 6 | GitHub reconnect | Restarts GitHub App connection. | Disabled offline. | GitHub App |

## 13. Settings - AI Models

![Settings - AI Models](./13-settings-ai-models.png)

Purpose: Task-specific model routing and provider setup.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Refresh models | Reloads model inventory. | Shows provider failures inline. | Model registry |
| 2 | Choose local/cloud/provider | Selects routing preference. | Disabled if provider unavailable. | Model gateway |
| 3 | Save preferences | Persists model routing. | Requires account/backend. | Settings API |
| 4 | Test local model | Runs local model smoke test. | Disabled if Ollama/runtime missing. | Local provider |
| 5 | Connect provider | Opens provider credential flow. | Requires vault/account. | Privacy vault |
| 6 | Cloud fallback toggle | Enables cloud fallback when local fails. | Disabled if no cloud provider. | Model router |

## 14. Settings - Privacy Vault

![Settings - Privacy Vault](./14-settings-privacy-vault.png)

Purpose: Local encrypted credential storage.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Create vault | Initializes encrypted local vault. | Disabled if vault exists. | Encryption key |
| 2 | Unlock vault | Unlocks vault for session. | Shows invalid key state. | Local secret |
| 3 | Lock vault | Clears decrypted keys from memory. | Disabled when locked. | Vault state |
| 4 | Reset local key | Starts destructive reset flow. | Confirmation required. | Local vault |
| 5 | Recovery note | Opens recovery guidance. | Always available. | Docs |
| 6 | Back to Code settings | Returns to Code tab. | Always available. | Frontend state |

## 15. Download Page

![Download Page](./15-download-page.png)

Purpose: Installer availability, checksum, and release links.

| # | Button / state | Click behavior | Disabled/error state | Dependency |
| --- | --- | --- | --- | --- |
| 1 | Download Windows installer | Downloads `.exe` installer. | `Installer unavailable - release artifact missing`. | Release manifest |
| 2 | Copy SHA256 | Copies checksum. | Disabled/pending until checksum exists. | Manifest checksum |
| 3 | View release notes | Opens release notes. | Uses docs fallback if URL missing. | Release notes URL |
| 4 | Windows tab | Shows Windows installer instructions. | Always available. | Frontend state |
| 5 | macOS tab | Shows macOS pending/download state. | Pending until artifacts exist. | Release manifest |
| 6 | Linux tab | Shows Linux pending/download state. | Pending until artifacts exist. | Release manifest |

## Review Status

| Check | Status |
| --- | --- |
| 15 PNG files present | Pass |
| Each screenshot has a documented intent | Pass |
| Each screenshot has documented button behavior | Pass |
| Disabled/offline states documented | Pass |
| API/runtime dependencies documented | Pass |
| Electron Code-only constraints documented | Pass |
