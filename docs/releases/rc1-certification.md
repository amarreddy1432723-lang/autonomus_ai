# Arceus RC1 Certification

| Field | Value |
| --- | --- |
| Build | 0.1.0-alpha |
| Overall | PASS |
| Generated | 2026-07-28T07:32:44.1233505Z |
| Hosted Frontend | https://frontend-production-fbde.up.railway.app |
| Hosted Backend | https://agent-production-8568.up.railway.app |
| Auth Backend | https://auth-production-dae4.up.railway.app |
| Runtime Frontend | https://frontend-production-fbde.up.railway.app |
| Runtime Backend | http://127.0.0.1:8003 |
| Duration | 71.32 seconds |
| Blockers | 0 |
| Warnings | 0 |

## Phase Results

| Phase | Status | Seconds | Detail |
| --- | --- | ---: | --- |
| Website and download | PASS | 2.14 |  |
| Alpha readiness surface | PASS | 0.68 |  |
| Desktop route isolation | PASS | 5.71 |  |
| Installation and launch | PASS | 43.13 |  |
| Authentication surface | PASS | 2.2 |  |
| Repository to runtime proof | PASS | 16.84 |  |
| Recovery proof | PASS | 0.4 |  |
| Performance budget | PASS | 0.03 |  |

## Certification Checks

| Phase | Check | Status | Severity | Detail |
| --- | --- | --- | --- | --- |
| Website and download | Download page reachable | PASS | ok | https://frontend-production-fbde.up.railway.app/download - 200 OK |
| Website and download | Download manifest reachable | PASS | ok | https://agent-production-8568.up.railway.app/api/v1/downloads/latest - 200 OK |
| Website and download | Windows installer available in manifest | PASS | ok | https://github.com/amarreddy1432723-lang/autonomus_ai/releases/download/arceus-code-v1.0.0/Arceus-Code-1.0.0-Setup.exe |
| Alpha readiness surface | Summary has no blocker failures | PASS | ok | 0 blocker failure(s) in C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-alpha-release-summary.json |
| Desktop route isolation | Summary has no blocker failures | PASS | ok | 0 blocker failure(s) in C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-desktop-isolation-summary.json |
| Installation and launch | Summary has no blocker failures | PASS | ok | 0 blocker failure(s) in C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-installed-product-summary.json |
| Authentication surface | Sign-in page reachable | PASS | ok | https://frontend-production-fbde.up.railway.app/sign-in - 200 OK |
| Authentication surface | Sign-up page reachable | PASS | ok | https://frontend-production-fbde.up.railway.app/sign-up - 200 OK |
| Authentication surface | Protected auth API rejects missing token | PASS | ok | https://auth-production-dae4.up.railway.app/api/v1/auth/me - The remote server returned an error: (401) Unauthorized. |
| Local runtime startup | Agent runtime already reachable | PASS | ok | http://127.0.0.1:8003/api/v1/health - 200 OK |
| Repository to runtime proof | Summary has no blocker failures | PASS | ok | 0 blocker failure(s) in C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-core-loop-summary.json |
| Recovery proof | Interrupted execution recovery checks pass | PASS | ok | checks=13; failed=0 |
| Performance budget | Desktop launch evidence captured | PASS | ok | pid=31640; live=5; window=1 |

## Artifacts

- summary: C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-alpha-release-summary.json - Alpha readiness surface summary
- summary: C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-desktop-isolation-summary.json - Desktop route isolation summary
- summary: C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-installed-product-summary.json - Installation and launch summary
- summary: C:\Users\amarn\OneDrive\Desktop\my ai\.verify\rc-core-loop-summary.json - Repository to runtime proof summary

## Exit Criteria

- Packaged Windows application completes the release flow.
- Hosted control plane is reachable.
- Repository analysis, mission compilation, scheduler, worker, evidence, change-set, apply, rollback, and recovery proofs pass.
- Desktop Alpha route isolation remains enforced.
