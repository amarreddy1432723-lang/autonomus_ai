# API Reference

Arceus exposes OpenAPI at the FastAPI service docs endpoint in development:

```text
http://localhost:8003/docs
```

Important endpoint groups:

- `/api/v1/code/projects`
- `/api/v1/code/sessions`
- `/api/v1/code/jobs`
- `/api/v1/code/terminal`
- `/api/v1/github`
- `/api/v1/plugins`
- `/api/v1/auth/sso`
- `/api/v1/admin`
- `/api/v1/billing`

Production API responses should include clear status, job, activity, artifacts, and usage metadata where relevant.
