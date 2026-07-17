# Arceus Code Button-State Audit

This audit is the source of truth for the installed Arceus Code desktop controls. Buttons should be visible only when they belong to Code, should explain disabled states, and should never expose Product Hub, PA, Interview, or Admin inside Electron.

## Global Shell

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Logo | Always | Never opens product switcher in Electron | Opens `/workspace` |
| Command search | Always | If no command match, searches workspace | Runs first Code command or opens workspace search |
| Status pill | Always | Shows `Connect account`, `Local mode`, `Agent offline`, or `Partial` | Connects account for auth-required; otherwise retries health |
| Account | Electron auth missing | `Connect account` | Opens `/auth/desktop` |
| Notifications | Always | Badge only for Code approvals/issues | Opens notification surface when implemented |

## Workspace Left Sidebar

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Open Folder | Electron desktop available | Disabled while busy | Native folder picker, create/reopen trusted project |
| New Chat | Active project exists or backend available | Disabled while busy | Creates project-scoped chat |
| Search | Always | None | Focuses workspace command/search |
| Explorer | Always | Local-only still works | Opens right file tree drawer |
| Toggle Editor | Always | None | Shows/hides Monaco editor |
| Merge | Exactly 2 projects selected | Disabled with fewer/more selections | Creates new merged project, originals untouched |
| Close Project | Project open | Never deletes disk files | Removes from open-project list |
| Remove from App | Project exists | Confirmation required | Archives app project only |

## Right Rail

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Explorer | Always | Shows local tree when API offline | Opens folder structure drawer |
| Terminal | Always | If no folder and API offline, asks to open folder | Toggles bottom terminal panel |
| Changes | Always | Badge only for review-required changes | Opens diff/history drawer |
| Jobs | Always | Worker disabled shown as status, not crash | Opens durable job rows/logs |
| Preview | Preview state exists or can start | Cloud preview disabled offline | Opens iframe/screenshots/errors |
| Git / PR | GitHub connected and approved changes exist | Prompts Connect GitHub | Opens repo, branch, commit, PR checks |
| Apps | Always | Provider actions disabled when unavailable | Opens connector list |
| Tasks | Suggestions available | Empty state when none | Opens next-action tasks |

## Bottom Terminal

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| New Terminal | Trusted folder or backend terminal available | `Open a folder to start local terminal` | Creates local PTY first, backend fallback second |
| Shell Selector | Terminal panel open | Local profile persists | Chooses PowerShell/Bash/Zsh profile |
| Search | Output exists | Empty output shows 0 matches | Searches xterm/output buffer |
| Copy | Output exists | Disabled when no output | Copies selected/output text and flashes copied state |
| Clear | Active terminal exists | Disabled without terminal | Clears terminal buffer |
| Restart | Active terminal exists and not busy | Disabled while busy | Restarts terminal in same cwd |
| Kill | Active terminal running | Disabled when killed/no terminal | Kills active process/session |
| Resize | Panel open | None | Compact/half/max |
| Close | Panel open | None | Hides terminal, sessions remain |

## Changes / Diff Review

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Undo changes | Rollback snapshot exists | Hidden when no rollback | Calls rollback and refreshes tree/editor |
| Accept hunk | Review-required patch exists | Disabled when no patch/conflict blocks | Marks hunk accepted |
| Reject hunk | Review-required patch exists | Disabled when no patch | Marks hunk rejected |
| Apply selected | At least one accepted hunk/file | Disabled when all hunks rejected | Applies selected hunks only |
| Reset review | Patch exists | Disabled when no patch | Clears review state |

## Jobs

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Refresh jobs | Always | Shows worker disabled/offline state | Reloads job list/status |
| Pause | Job running | Hidden otherwise | Pauses/revokes active job |
| Resume | Job paused | Hidden otherwise | Resumes/requeues job |
| Cancel | Job running/queued/paused | Hidden when terminal state | Cancels job |
| Retry | Job failed/timeout/dead-letter | Hidden otherwise | Requeues job |
| View logs | Job has logs | Empty state if none | Opens job log/artifacts |

## Preview

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Start preview | Runtime available | Disabled offline/no project | Starts dev server/runtime |
| Re-verify | Preview URL exists | Disabled without URL | Runs Playwright verification |
| Fix preview issue | Console/network/blank evidence exists | Disabled with no evidence | Sends evidence to agent for patch |
| Open external | Preview URL exists | Disabled without URL | Opens browser URL |

## Git

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Connect GitHub | No installation | Disabled while busy | Starts GitHub App install |
| Repo picker | GitHub connected | Disabled until connected | Selects installation repo |
| Create branch | Repo selected and branch valid | Shows branch validation | Creates branch from base |
| Commit approved changes | Approved, fresh changes exist | Blocks stale/conflicted patches | Commits approved hunks only |
| Open PR | Branch/commit ready | Disabled until commit branch exists | Opens PR |
| Refresh checks | PR exists | Disabled until PR exists | Polls CI checks |

## Settings

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Arceus Code tab | Electron desktop | Always visible | Code project/tool settings |
| AI Models tab | Electron desktop | Local test disabled if runtime unavailable | Local/cloud/provider model preferences |
| Privacy Vault tab | Electron desktop | Requires local key setup | Create/unlock/lock/reset vault |
| Suite settings | Web only | Hidden in Electron | PA/Interview/Admin settings stay web-only |

## Download

| Control | Enabled When | Disabled / Recovery State | Click Behavior |
| --- | --- | --- | --- |
| Download Windows Installer | Manifest item is `available=true` | `Installer unavailable - release artifact missing` | Downloads `.exe` |
| Copy SHA256 | Checksum exists | Shows pending checksum text | Copies checksum when added |
| View release notes | Notes URL configured | Links docs fallback | Opens release notes |
| OS tabs | Always | None | Switches installer instructions |
