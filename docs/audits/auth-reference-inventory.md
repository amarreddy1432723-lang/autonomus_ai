# Arceus Auth Reference Inventory

Canonical authentication is Clerk hosted web authentication with backend Clerk JWT verification. Desktop authentication is a compatibility bridge: a Clerk-authenticated browser session creates a short-lived one-time desktop exchange code, and the installed Electron app exchanges it for an Arceus desktop API session.

| Location | Reference | Runtime usage | Classification | Migration action | Status |
|---|---|---|---|---|---|
| `frontend/src/proxy.ts` | `clerkMiddleware`, `/sign-in`, `/sign-up` | Protects hosted web routes and delegates auth redirects to Clerk | B. Canonical new authentication | Keep and tighten route list | Updated |
| `frontend/src/proxy.ts` | `/workspace(.*)` public route | Allowed signed-out hosted web users into workspace | A. Legacy/incorrect guard behavior | Remove from public web routes; allow only Electron UA local shell route | Updated |
| `frontend/src/proxy.ts` | `/login`, `/signup` aliases | Old URLs should reach canonical Clerk pages | C. Compatibility redirect | Add aliases to public route list so redirect pages can run | Updated |
| `frontend/src/app/sign-in/[[...sign-in]]/page.tsx` | Clerk `<SignIn />` | Canonical web sign-in page | B. Canonical new authentication | Keep | Verified |
| `frontend/src/app/sign-up/[[...sign-up]]/page.tsx` | Clerk `<SignUp />` | Canonical web sign-up page | B. Canonical new authentication | Keep | Verified |
| `frontend/src/app/login/page.tsx` | Redirect to `/sign-in` | Compatibility URL for old links | C. Compatibility bridge | Keep deliberate redirect | Verified |
| `frontend/src/app/signup/page.tsx` | Redirect to `/sign-up` | Compatibility URL for old links | C. Compatibility bridge | Keep deliberate redirect | Verified |
| `frontend/src/app/auth/desktop/page.tsx` | `/api/v1/auth/desktop/code` | Browser side of desktop account connection | B. Canonical desktop handoff | Keep | Verified |
| `frontend/src/components/DesktopAuthBridge.tsx` | `/api/v1/auth/desktop/exchange` | Electron receives deep link code and exchanges it | B. Canonical desktop handoff | Keep | Verified |
| `frontend/src/utils/api.ts` | Clerk `window.Clerk.session.getToken()` | Web API requests attach Clerk bearer token | B. Canonical new authentication | Keep | Verified |
| `frontend/src/utils/api.ts` | Desktop bearer token from `desktopAuth` | Desktop API requests attach desktop session token | C. Compatibility bridge | Keep, hydrate from secure Electron storage | Updated |
| `frontend/src/utils/desktopAuth.ts` | `localStorage` token keys | Previously stored desktop tokens in renderer storage | A. Legacy storage behavior | Prefer Electron secure storage; clear legacy localStorage in desktop | Updated |
| `frontend/src/components/AppShell.tsx` | Clerk `UserButton`; desktop Connect account | Shows account state in web and desktop shells | B. Canonical UX | Hydrate desktop state from secure bridge | Updated |
| `desktop/main.js` | `arceus://auth/callback` | Receives desktop authentication code | B. Canonical desktop handoff | Keep | Verified |
| `desktop/main.js` | `safeStorage` auth session file | Encrypted desktop session persistence where supported | B. Canonical desktop storage | Add narrow IPC read/write/clear bridge | Updated |
| `desktop/preload.js` | `desktopAuth.read/write/clear` | Renderer access to secure desktop auth session | B. Canonical desktop storage bridge | Add narrow bridge only | Updated |
| `backend/services/shared/security.py` | `verify_clerk_token`, JWKS, `auth_provider_id=sub` | Server-side provider verification and user mapping | B. Canonical new authentication | Keep | Verified |
| `backend/services/auth/main.py` | `/api/v1/auth/desktop/code` | Creates desktop exchange code after authenticated user resolution | B. Canonical desktop handoff | Keep, make code opaque and one-time | Updated |
| `backend/services/auth/main.py` | `/api/v1/auth/desktop/exchange` | Exchanges desktop code for desktop API session | B/C. Canonical desktop bridge | Keep, reject reused/expired/invalid codes | Updated |
| `backend/services/shared/models.py` | `DesktopAuthCode` | Stores desktop exchange code checksums and consumed state | B. Canonical desktop bridge persistence | Add model and indexes | Updated |
| `backend/migrations/versions/w0f1g2h3i4j5_desktop_auth_codes.py` | `desktop_auth_codes` table | Persists one-time desktop exchange records | B. Canonical desktop bridge persistence | Add reversible migration | Added |
| `backend/services/auth/main.py` | `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`, JWT sessions | Legacy email/password API and desktop session compatibility | C. Compatibility bridge | Retain until desktop sessions are replaced by provider-bound session strategy | Retained |
| `backend/services/shared/security.py` | `x-user-id` dev fallback | Local/demo development fallback | C. Compatibility bridge | Keep disabled in production/staging via existing environment checks | Verified |
| `frontend/src/utils/api.ts` | `x-user-id` demo header | Demo fallback when auth is not required | C. Compatibility bridge | Keep disabled in production-like frontend | Verified |
| `scripts/verify-prototype-p0.ps1` | Desktop auth static checks | Existing P0 auth surface verification | B. Verification | Keep | Verified |
| `scripts/verify-auth-migration.ps1` | Auth migration verifier | New explicit auth migration gate | B. Verification | Add | Added |

## Browser Baseline Summary

Initial Chrome baseline showed canonical Clerk routes at `/sign-in` and `/sign-up`, but hosted `/workspace` was reachable signed out because the route was listed as public in the proxy. `/onboarding`, `/mission-control`, `/settings`, `/login`, and `/signup` redirected to Clerk sign-in. That established `/workspace` as the verified guard defect fixed in this slice.
