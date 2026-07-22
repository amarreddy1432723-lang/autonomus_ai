# Workspace Inventory

This inventory tracks the live `/workspace` redesign target. The route currently returns `ArceusMissionWorkspace` before the legacy workspace logic in `page.tsx`, so `ArceusMissionWorkspace.tsx` is the active desktop surface.

## Route And Live Components

| Surface | File | Classification | Notes |
| --- | --- | --- | --- |
| Workspace route | `frontend/src/app/workspace/page.tsx` | Keep logic, split later | Contains legacy editor, terminal, patch, API, and agent orchestration, but the active return is `ArceusMissionWorkspace`. |
| Live workspace | `frontend/src/app/workspace/ArceusMissionWorkspace.tsx` | Replace visual shell | Was dark mission-control UI with broad OS navigation. Reworked as Arceus Code-only workspace. |
| Live workspace CSS | `frontend/src/app/workspace/ArceusMissionWorkspace.module.css` | Replace theme | Old gradient/glass/dark styles should not remain in the active screen. |
| Legacy CSS | `frontend/src/app/workspace/Workspace.module.css` | Restyle in phases | Large CSS file still supports legacy components and drawers. Avoid deleting until legacy route logic is fully extracted. |

## Preserve

| Capability | Current Area | Treatment |
| --- | --- | --- |
| File operations | `FileExplorer`, legacy page handlers | Keep logic. Restyle explorer rows only. |
| Editor | `EditorPanel` and Monaco integration | Keep logic. Wrap in new `EditorWorkspace` shell. |
| Terminal | `WorkspaceTerminalPanel` and Electron terminal bridge | Keep logic. Restyle and bind to bottom panel. |
| Agent messages and receipts | `ConversationPanel`, `WorkReceipt` | Keep logic. Move into AI Mission Panel. |
| Patch review | `ActivityPanel`, `DiffViewer`, rollback APIs | Keep logic. Expose through Changes panel only when needed. |
| Service health | `ServiceRecoveryBanner`, `serviceHealth` | Keep logic. Surface as top status and recovery banner. |

## Replace Or Hide In Desktop Code

| Item | Reason |
| --- | --- |
| Product Hub / PA / Interview / Admin navigation | Desktop app is Arceus Code only. |
| Public Login / Sign up header buttons | Electron needs account connection state, not web marketing auth clutter. |
| Analytics-style mission cards | The workspace should be file/editor/task focused, not a dashboard. |
| Dark gradient/glow theme | The redesign standard is light, quiet, and code-work oriented. |

## New Layout State

The new persisted layout store is `frontend/src/stores/workspace-layout-store.ts`.

Persist key: `arceus.workspace.layout.v1`

Managed state:

- active primary sidebar view
- active bottom panel view
- sidebar, AI panel, and bottom panel visibility
- sidebar width
- AI panel width
- bottom panel height

Size limits:

| Panel | Min | Default | Max |
| --- | ---: | ---: | ---: |
| Sidebar | 180 | 240 | 420 |
| AI panel | 280 | 360 | 560 |
| Bottom panel | 120 | 220 | 500 |

## New Shell Components

| Component | Purpose |
| --- | --- |
| `AppShell` | Layout-only grid shell. No business logic. |
| `WorkspaceTopBar` | Arceus Code, project, search, model/status/account controls. |
| `ActivityBar` | Icon-only Explorer/Search/Source Control/Missions/Extensions/Settings rail. |
| `WorkspaceSidebar` | Generic sidebar frame for Explorer/Search/etc. |
| `EditorWorkspace` | Editor frame and empty state. |
| `BottomPanel` | Terminal/problems/output/tests/logs frame. |
| `WorkspaceStatusBar` | Branch, diagnostics, services, model health. |

## Next Extraction Targets

1. Move legacy file tree state from `page.tsx` into an explorer hook.
2. Move terminal orchestration into a terminal hook and render it inside `BottomPanel`.
3. Move chat/agent orchestration into an AI Mission Panel component.
4. Replace legacy right rail with shell-driven panel views.
5. Remove dead code from `page.tsx` after feature parity is confirmed.
