# Arceus Alpha Technical Audit - 2026-07-28

## Executive Verdict

Arceus is no longer primarily blocked by missing backend runtime primitives. The critical mission-to-change-set review path exists in the repo:

Repository -> Mission -> Scheduler -> Desktop worker -> Change set artifact -> Mission Control -> Review -> Filesystem execute -> Rollback.

The largest Alpha risk is now product cleanup: too many suite-era, experimental, and static storyboard routes remain visible in the same codebase as the real Arceus Code desktop experience.

## Evidence Checked

- Route inventory under `frontend/src/app`.
- Desktop shell and route guard in `frontend/src/components/AppShell.tsx`, `frontend/src/components/DesktopCodeRouteGuard.tsx`, and `frontend/src/lib/frontendBoundaries.ts`.
- Mission Control real endpoint wiring in `frontend/src/app/mission-control/page.tsx`.
- Workspace project persistence in `frontend/src/app/workspace/page.tsx`.
- Backend change-set executor and review endpoints under `backend/services/agent/arceus_runtime/evidence/routes.py`.
- Current dirty worktree status.

## Route Inventory

Detected 55 page routes:

`/admin`, `/ai-workforce`, `/analytics`, `/approvals`, `/architecture-strategy`, `/auth/desktop`, `/calendar`, `/chat`, `/dashboard`, `/deploy`, `/design`, `/docs`, `/domain-intelligence`, `/download`, `/engineering-roadmap`, `/enterprise`, `/evolution-center`, `/executive-review`, `/goals`, `/hub`, `/idea-discovery`, `/intelligence`, `/intelligence-kernel`, `/internet`, `/interview`, `/knowledge-graph`, `/launch`, `/launcher`, `/life-graph`, `/login`, `/marketplace`, `/memory`, `/mission-control`, `/onboarding`, `/organization-network`, `/pa`, `/pa/planner`, `/pa/reflection`, `/pricing`, `/product-blueprint`, `/product-intelligence`, `/products`, `/products/code`, `/products/interview`, `/products/pa`, `/settings`, `/sign-in/[[...sign-in]]`, `/sign-up/[[...sign-up]]`, `/signup`, `/studio`, `/tasks`, `/technology-stack`, `/timeline`, `/ui-preview/arceus-code`, `/workspace`.

## Route Classification

### Keep For Alpha

- `/launch`: desktop entry screen.
- `/onboarding`: folder/repo/mission setup.
- `/workspace`: core local workspace.
- `/mission-control`: runtime, evidence, review, execute, rollback surface.
- `/settings`: desktop account/system/model settings, but needs scope cleanup.
- `/auth/desktop`: desktop account handoff.
- `/download`: public installer delivery.
- `/products/code`, `/pricing`, `/sign-in`, `/sign-up`: web-only public/customer flow.

### Redesign Or Merge Before Alpha

- `/idea-discovery`, `/product-intelligence`, `/product-blueprint`, `/architecture-strategy`, `/technology-stack`, `/engineering-roadmap`, `/ai-workforce`, `/executive-review`.

These match the desired premium journey, but they are currently mostly static page-level experiences with local constants. They should either be connected to real mission/product APIs or treated as guided onboarding screens only.

### Hide From Desktop Immediately

- `/admin`, `/hub`, `/pa`, `/pa/planner`, `/pa/reflection`, `/interview`, `/products/pa`, `/products/interview`, `/dashboard`, `/analytics`, `/calendar`, `/life-graph`, `/internet`, `/memory`, `/goals`, `/approvals`, `/deploy`, `/design`, `/intelligence`, `/marketplace`, `/studio`, `/tasks`, `/timeline`, `/launcher`, `/login`, `/signup`, `/enterprise`, `/docs`.

Many can remain in the web app or internal admin, but they should not appear inside the installed Arceus Code desktop shell.

### Developer-Only

- `/ui-preview/arceus-code`.

Keep behind `NEXT_PUBLIC_ENABLE_UI_PREVIEWS=true`.

## Critical Findings

1. Desktop route guard exists, but it still allows many vision pages: `/evolution-center`, `/knowledge-graph`, `/organization-network`, `/intelligence-kernel`, and `/domain-intelligence`. These are not needed for Alpha and increase confusion.

2. The shell is partially cleaned for Electron. `AppShell.tsx` hides Product Hub, PA, Interview, and Admin in Electron, and logo click routes to `/workspace`. This addresses the old screenshot complaint, but the shared shell still contains demo auth and public Login/Sign up branches for web.

3. Mission Control is now real enough for Alpha validation. It loads persisted artifact version content, calls `/change-set/review`, and calls `/change-set/execute` for apply/rollback with `workspace_root`.

4. Several planning journey pages are static. They define local arrays such as `STAGES`, `BLUEPRINT_CARDS`, `ARCHITECTURES`, `MILESTONES`, `SPECIALISTS`, and `SUMMARY`. This is acceptable as guided prototype UI, but not as a claimed live AI planning engine.

5. The installed app depends on the hosted Railway frontend. Local frontend fixes will not appear in the installer until the frontend is deployed and the installer is rebuilt or configured to point at the updated hosted app.

6. The worktree is dirty with many unrelated files. Production cleanup should be committed by module, not with `git add .`.

## Alpha Readiness Scorecard

| Area | Score | Status |
| --- | ---: | --- |
| Runtime backend | 90% | Real durable mission/task/change-set primitives exist. |
| Mission Control review/apply/rollback | 84% | Real endpoints wired; still needs installed-app proof loop. |
| Desktop launch/download/install | 84% | Installer and manifest path work; signing remains external. |
| Workspace local loop | 82% | Folder, editor, terminal are strong; needs installed QA proof. |
| Auth | 70% | Desktop auth exists; real Clerk persistence still needs proof. |
| UI coherence | 58% | New design exists, but legacy/suite routes dilute product. |
| Planning journey | 55% | Beautiful screens, mostly static until tied to mission APIs. |
| Release readiness | 78% | Repo verifier exists; external env/signing/deploy must be proven. |
| Alpha overall | 78% | Real product exists; cleanup and packaged proof are next. |

## P0 Alpha Blockers

1. Deploy the latest frontend to Railway.
2. Run installed app against hosted frontend and prove Mission Control apply/rollback.
3. Restrict Electron desktop route allowlist to Arceus Code Alpha routes only.
4. Remove or hide PA, Interview, Hub, broad dashboard, and legacy suite routes from desktop navigation.
5. Prove real Clerk desktop sign-in, restart persistence, sign-out, and expired-session reauth.
6. Run real local repository mission: open folder -> analyze -> create mission -> worker produces change set -> approve -> filesystem apply -> rollback.
7. Rebuild installer and update public manifest checksum after the frontend/desktop cleanup.

## Recommended Cleanup Order

1. Route cleanup and desktop allowlist tightening.
2. Settings cleanup to Code-only tabs.
3. Mission Control installed-app proof loop.
4. Convert static planning journey pages into API-backed mission stages, or hide them behind prototype mode.
5. Commit by module: desktop shell, frontend routes, Mission Control, backend executor, verification scripts.

## Do Not Do Next

- Do not add another large backend subsystem.
- Do not add more flagship pages.
- Do not redesign the visual language again.
- Do not claim production readiness until the installed app passes the real proof loop.
