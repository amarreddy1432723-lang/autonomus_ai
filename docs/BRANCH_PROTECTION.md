# Recommended GitHub Branch Protection

Apply these rules to `main`:

- Require pull request before merging.
- Require at least one approving review.
- Require review from CODEOWNERS.
- Require status checks:
  - `backend`
  - `frontend`
  - `desktop`
  - `docker-images`
  - `security`
- Require branches to be up to date before merging.
- Block force pushes.
- Block deletions.
- Allow admins to bypass only for documented incidents.
