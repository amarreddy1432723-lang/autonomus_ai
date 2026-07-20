# Arceus Frontend Architecture

This implementation starts Book II Part 31 with code-level foundations instead of a risky one-shot monorepo migration.

## Implemented Foundations

- Product surface boundaries for web, desktop, admin, auth, and docs.
- Shared TypeScript contracts for missions, agents, approvals, files, commands, conversations, and desktop capabilities.
- Shared design tokens exported from TypeScript and backed by CSS variables.
- Typed query-key hierarchy for TanStack Query.
- Normalized frontend error model with retryability and request IDs.
- Base API client with auth headers, request IDs, timeout, error normalization, and telemetry hooks.
- Mission client interface as the first domain-client example.
- Feature flag registry with owner, description, rollout, and expiration fields.
- Dedicated Zustand stores for layout, workspace, and notifications.
- First shared UI primitives: Button and Badge.

## Deliberate Non-Migration

The current repo still uses `frontend/` and `desktop/` instead of moving to `apps/web`, `apps/desktop`, and `packages/*`. That migration should be a separate branch because it will touch build, deployment, Electron paths, Railway settings, and installer packaging.

## Next Frontend Migration Steps

1. Move reusable UI into `frontend/src/components/ui` until the workspace split is ready.
2. Replace direct `apiRequest` calls in feature pages with domain clients.
3. Move workspace state out of `frontend/src/app/workspace/page.tsx` into scoped hooks and stores.
4. Add command registry around the `Command` type.
5. Add notification center UI using `useNotificationStore`.
6. Add test coverage for API error normalization, route boundaries, and desktop allowed routes.
7. Plan the actual `apps/*` and `packages/*` migration after the desktop proof loop is stable.

