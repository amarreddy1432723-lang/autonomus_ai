# Arceus Frontend Redesign Inventory

This inventory tracks the migration from the older premium-blue suite UI to the focused Arceus Code developer workspace. Existing functionality should be hidden or restyled before it is removed.

| Area | Route / Surface | Classification | Notes |
| --- | --- | --- | --- |
| Public landing | `/` | REDESIGN | Keep as web marketing, but simplify visuals after Code surfaces are stable. |
| Product pages | `/products/*` | HIDE from desktop | Remain web-only; not part of installed Arceus Code navigation. |
| Download | `/download` | REDESIGN | Converted to the minimal light release/download surface. |
| Desktop welcome | `/launch` | REDESIGN | Converted to the first-pass minimal Code start page. |
| Editor workspace | `/workspace` | KEEP + REDESIGN SHELL | Preserve local folder/editor/terminal/agent functionality. Continue reducing dark/card-heavy styling. |
| AI assistant | `/workspace` AI panel | REDESIGN | Move toward structured mission, plan, changes, agents tabs. |
| Settings | `/settings` | SIMPLIFY | Desktop should show Code, AI Models, Privacy/Account only. Web may keep billing/admin areas. |
| Billing | `/pricing`, billing settings | KEEP + SIMPLIFY | Must retain quota/subscription behavior; visual simplification pending. |
| Admin | `/admin` | KEEP SEPARATE | Admin-only operational surface; never normal desktop navigation. |
| Arceus PA | `/pa`, `/pa/*` | HIDE from Code app | Separate product. |
| Arceus Interview | `/interview`, `/products/interview` | HIDE from Code app | Separate product. |
| Dashboard widgets | `/dashboard`, broad hub widgets | HIDE | Not part of Code desktop MVP. |
| Mission planning screens | `/idea-discovery` through `/mission-control` | REDESIGN | Keep flow, align all screens to light minimal system. |
| Evolution/knowledge screens | `/evolution-center`, `/knowledge-graph`, `/organization-network`, `/intelligence-kernel` | DEFER | Strategic screens, not core Code MVP path. |
| Authentication | `/sign-in`, `/sign-up`, `/auth/desktop` | SIMPLIFY | Centered account connection flow. Desktop must show account state, not public login clutter. |
| Shared shell | `frontend/src/components/AppShell.*` | REDESIGN | Light topbar/activity shell started. |
| Global theme | `frontend/src/styles/tokens.css` | KEEP | New central light design system tokens. |

## Migration Checklist

- [x] Create central light design tokens.
- [x] Replace dark-first global theme defaults.
- [x] Make desktop route guard light/minimal.
- [x] Simplify desktop launch screen.
- [x] Simplify download page.
- [ ] Finish AppShell responsive activity bar and file explorer layout.
- [ ] Redesign workspace CSS around editor-first layout.
- [ ] Redesign AI assistant panel as mission/work receipt surface.
- [ ] Simplify Settings to Account, Appearance, AI Models, Integrations, Editor, Billing, Privacy, About.
- [ ] Simplify login/sign-up/desktop auth.
- [ ] Audit and remove old gradients, glow, glass, and blue-heavy styles route by route.
- [ ] Add visual regression screenshots for launch, download, settings, workspace, and auth.
