## Summary
- What changed:
- Why it changed:
- Product area: Code / PA / Interview / Platform

## Safety Checklist
- [ ] Backend migrations are included or not needed.
- [ ] Auth, billing, and product-scope behavior are unchanged or tested.
- [ ] User data, secrets, and local filesystem access are protected.
- [ ] Rollback path is documented for risky changes.

## Verification
- [ ] `python -m compileall backend/services`
- [ ] `python -m pytest backend`
- [ ] `npm run lint` in `frontend`
- [ ] `npm run build` in `frontend`
- [ ] `node --check desktop/main.js`
- [ ] `node --check desktop/preload.js`

## Screenshots / Notes
Add screenshots for UI changes and links to logs for infrastructure changes.
