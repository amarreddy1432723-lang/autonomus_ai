# Arceus Auth Migration Report

## 1. Previous Authentication Architecture

Arceus had a mixed authentication surface:

- Clerk was already present for web sign-in/sign-up and backend token verification.
- The auth service still exposed email/password JWT routes: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`, and `/api/v1/auth/logout`.
- Desktop handoff used `/api/v1/auth/desktop/code` and `/api/v1/auth/desktop/exchange`, but the exchange code was a reusable signed JWT until expiry.
- Electron renderer state stored desktop API tokens in browser `localStorage`.
- Hosted `/workspace` was listed as a public web route, so signed-out web users could reach the workspace shell.

## 2. New Canonical Architecture

Canonical authentication is now:

```text
Clerk hosted web auth
  -> frontend receives Clerk session
  -> frontend calls backend with Clerk bearer token
  -> backend validates Clerk token and maps Clerk subject to one Arceus user
  -> browser desktop-auth page creates an opaque one-time exchange code
  -> Electron receives arceus://auth/callback?code=...
  -> Electron exchanges the code exactly once
  -> backend returns a desktop API session
  -> Electron stores the desktop session through safeStorage where available
```

The email/password JWT endpoints remain a compatibility bridge for existing local/dev and desktop-session behavior. They are not the canonical public web sign-in path.

## 3. Legacy References Found

See [auth-reference-inventory.md](auth-reference-inventory.md).

Key findings:

- No active Firebase auth references were found by `scripts/verify-auth-migration.ps1`.
- `/login` and `/signup` exist as compatibility redirects to Clerk routes.
- JWT login/register routes remain active compatibility endpoints.
- `x-user-id` remains a development fallback and is disabled in production-like auth paths by existing environment checks.

## 4. Legacy References Removed

No broad legacy endpoints were removed in this slice. That was intentional: desktop exchange and local/dev compatibility still depend on the auth service JWT session format. The unsafe behavior removed was:

- reusable stateless desktop auth exchange code
- plain localStorage-first desktop token persistence in Electron
- public web access classification for `/workspace`

## 5. Compatibility Redirects Retained

- `/login` -> `/sign-in`
- `/signup` -> `/sign-up`

These are now explicitly public in the proxy so the redirect pages can run instead of being intercepted before redirect.

## 6. Database Changes

Added `DesktopAuthCode` and migration:

- `backend/services/shared/models.py`
- `backend/migrations/versions/w0f1g2h3i4j5_desktop_auth_codes.py`

The table stores:

- `code_hash`
- `user_id`
- `redirect_uri`
- request metadata
- `expires_at`
- `consumed_at`

Raw exchange codes are not stored.

## 7. Frontend Changes

- `frontend/src/proxy.ts`
  - removed `/workspace(.*)` from public web routes
  - added `/login(.*)` and `/signup(.*)` public aliases
  - added Electron-only allowance for desktop local shell routes
- `frontend/src/utils/desktopAuth.ts`
  - added secure Electron hydration path
  - clears legacy localStorage token keys in Electron
- `frontend/src/utils/api.ts`
  - hydrates desktop auth state before building async API headers
- `frontend/src/components/AppShell.tsx`
  - hydrates desktop account state from the secure desktop bridge

## 8. Backend Changes

- `backend/services/auth/main.py`
  - replaced JWT desktop auth code generation with opaque random code generation
  - stores only SHA-256 code checksum
  - rejects expired, invalid, and reused codes
- `backend/test_desktop_auth_handoff.py`
  - verifies second exchange of the same code returns `401`

## 9. Desktop Changes

- `desktop/main.js`
  - added `safeStorage`-backed desktop auth session read/write/clear helpers
  - added narrow IPC handlers: `desktop.auth.read`, `desktop.auth.write`, `desktop.auth.clear`
- `desktop/preload.js`
  - exposes `electron.desktopAuth` and `arceusDesktop.auth`

## 10. Security Controls

- Backend verifies Clerk JWTs server-side through the existing shared security layer.
- Provider identity maps by provider subject, not email alone.
- Desktop exchange codes are opaque, short-lived, checksum-stored, and one-time.
- Desktop sessions use Electron `safeStorage` where encryption is available.
- Hosted `/workspace` is no longer classified as public for normal browsers.

## 11. Browser Routes Tested

Chrome route baseline written to:

`C:\Users\amarn\OneDrive\Desktop\my ai\.verify\screenshots\auth-migration\browser-baseline.json`

Routes walked:

- `/`
- `/download`
- `/sign-in`
- `/sign-up`
- `/auth/desktop`
- `/onboarding`
- `/workspace`
- `/mission-control`
- `/settings`
- `/login`
- `/signup`

Screenshots were saved in:

`C:\Users\amarn\OneDrive\Desktop\my ai\.verify\screenshots\auth-migration\`

Browser limitation: local dev did not show the real Clerk hosted form because `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` was not present in that local frontend process. `/sign-in` and `/sign-up` showed the configured fallback message. Therefore real web sign-in/sign-out remains externally unverified in this local browser run.

## 12. Desktop Flows Tested

Automated backend desktop handoff lifecycle passed:

- invalid redirect rejected
- valid desktop code created
- valid code exchanged successfully
- reused code rejected
- invalid code rejected

Full installed Electron sign-in was not completed in this slice because it requires an interactive Clerk browser session and the rebuilt/deployed frontend carrying these changes.

## 13. Commands Run

Passed:

```powershell
python -m pytest backend\test_desktop_auth_handoff.py -q
node --check desktop\main.js
node --check desktop\preload.js
python -m compileall backend\services
npm run build
.\scripts\verify-auth-migration.ps1 -RunBackendTests -CheckBrowserArtifacts
```

Failed then fixed:

```powershell
python -m pytest backend\test_desktop_auth_handoff.py -q
```

Initial failure: timezone-aware DB timestamp compared with naive `datetime.utcnow()`. Fixed in `_consume_desktop_auth_code`.

`scripts/verify-auth-migration.ps1` initially had PowerShell object construction issues. Fixed and re-run successfully.

## 14. Tests Passed

- Backend desktop auth handoff regression test
- Backend compile
- Electron main/preload syntax
- Frontend production build
- Auth migration verifier
- Chrome route baseline artifact generation

## 15. Tests Failed

No current focused auth migration tests are failing.

Unverified external flows:

- real Clerk web sign-in
- real Clerk web sign-out
- installed Electron account connect against deployed frontend
- desktop sign-out UX
- expired desktop session reauthentication in installed app

## 16. Remaining External Requirements

1. Deploy the frontend proxy/auth storage changes to Railway.
2. Run `clerk deploy` or confirm production Clerk instance envs on the deployed frontend.
3. Rebuild and upload a new desktop installer that contains the Electron secure-storage IPC bridge.
4. Complete interactive Clerk sign-in in Chrome.
5. Launch installed Arceus Code, connect account, restart, and confirm account persists.
6. Verify hosted `/workspace` redirects signed-out users after Railway deploy.

## 17. Final Verdict

`CONDITIONAL_PASS` for the implemented auth migration slice.

The source-level migration is complete for:

- canonical Clerk web auth boundary
- one-time desktop auth exchange
- safer Electron desktop session persistence
- explicit auth verification script and artifacts

The final production auth migration is not fully complete until deployed Clerk web sign-in/sign-out and installed desktop sign-in/sign-out are proven end to end.
