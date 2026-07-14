# Arceus Live Deployment Runbook

This runbook moves Arceus toward a private alpha with GitHub-controlled CI, staging, smoke tests, and production approval.

## Production Engineering Workflow

Arceus uses GitHub as the source of truth. Production changes should flow through:

```text
feature branch -> pull request -> CI -> staging -> smoke tests -> production approval -> release
```

Required release gates:

- Backend compile, tests, and Alembic migration check.
- Frontend lint and production build.
- Desktop syntax checks.
- Secret/dependency scans.
- Immutable Docker image build.
- Staging smoke tests against `/api/v1/health`, `/api/v1/ready`, and `/hub`.

See [RELEASE.md](./RELEASE.md) for rollback and release checklists.

## 1. Required Accounts

- Domain registrar or DNS provider
- Frontend host: Vercel
- Backend host: Render
- Render PostgreSQL with pgvector support
- Render Key Value / Redis
- LLM provider: OpenAI, Gemini, Groq, Anthropic, or compatible API
- Search provider key for live news/web lookup
- Error monitoring provider such as Sentry

This repository now includes:

- `render.yaml` for Render Blueprint deployment of auth, goals, agent, Postgres, and Redis.
- `frontend/vercel.json` for the Next.js Vercel project.
- `.github/workflows/ci.yml` for PR validation.
- `.github/workflows/release.yml` for image builds, environment gates, and smoke tests.
- `backend/Dockerfile` and `frontend/Dockerfile` for immutable container artifacts.
- `docker-compose.prod-smoke.yml` for production-like local smoke testing.

## 2. Production Environment

Set these outside the repository:

```bash
APP_ENV=production
ALLOW_DEMO_USER=false
ALLOW_DEV_AUTH_FALLBACK=false
NEXT_PUBLIC_REQUIRE_AUTH=true
DATABASE_URL=<managed-postgres-url>
REDIS_URL=<managed-redis-url>
JWT_SECRET=<strong-random-secret>
APP_ENCRYPTION_KEY=<strong-random-secret>
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=<real-key>
SERPER_API_KEY=<real-key>
NEXT_PUBLIC_AUTH_URL=https://my-ai-auth.onrender.com
NEXT_PUBLIC_GOALS_URL=https://my-ai-goals.onrender.com
NEXT_PUBLIC_AGENT_URL=https://my-ai-agent.onrender.com
```

Use equivalent provider keys if you choose Groq, Gemini, Anthropic, or a custom OpenAI-compatible server.

## 3. Render Backend

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Render will read `render.yaml` and create:
   - `my-ai-auth`
   - `my-ai-goals`
   - `my-ai-agent`
   - `my-ai-db`
   - `my-ai-redis`
   - `my-ai-production` env group
4. Fill the `sync: false` values in the `my-ai-production` env group:
   - `LLM_PROVIDER`
   - `LLM_MODEL`
   - `EMBEDDING_PROVIDER`
   - `EMBEDDING_MODEL`
   - provider API keys
   - `SERPER_API_KEY`
5. Deploy. The auth service runs `python -m alembic upgrade head` during pre-deploy.

Render service health checks:

```bash
curl https://my-ai-auth.onrender.com/api/v1/health
curl https://my-ai-goals.onrender.com/api/v1/health
curl https://my-ai-agent.onrender.com/api/v1/health
```

## 4. Vercel Frontend

1. Import the same GitHub repo into Vercel.
2. Set the Vercel project root directory to `frontend`.
3. Add these Vercel environment variables:

```bash
NEXT_PUBLIC_REQUIRE_AUTH=true
NEXT_PUBLIC_AUTH_URL=https://my-ai-auth.onrender.com
NEXT_PUBLIC_GOALS_URL=https://my-ai-goals.onrender.com
NEXT_PUBLIC_AGENT_URL=https://my-ai-agent.onrender.com
```

4. Deploy the Vercel project.

Local verification before deploy:

```bash
cd backend
python -m compileall services
python -m pytest -q
cd ../frontend
npm run build
```

## 5. Local Services

Run three backend processes:

```bash
uvicorn services.auth.main:app --host 0.0.0.0 --port 8001
uvicorn services.goals.main:app --host 0.0.0.0 --port 8002
uvicorn services.agent.main:app --host 0.0.0.0 --port 8003
```

Run the frontend:

```bash
cd frontend
npm ci
npm run build
npm run start
```

## 6. Launch Gate

Before inviting users, check:

```bash
curl https://my-ai-auth.onrender.com/api/v1/health
curl https://my-ai-goals.onrender.com/api/v1/health
curl https://my-ai-agent.onrender.com/api/v1/health
curl https://my-ai-auth.onrender.com/api/v1/architecture/system
curl https://my-ai-auth.onrender.com/api/v1/architecture/ai
curl https://my-ai-auth.onrender.com/api/v1/production/readiness
curl https://my-ai-auth.onrender.com/api/v1/future-roadmap
curl https://my-ai-auth.onrender.com/api/v1/evaluation/status
```

Do not invite users while `/api/v1/production/readiness` reports critical failures.

## 7. Private Alpha

- Invite 5-10 trusted users.
- Keep autonomy in observer mode by default.
- Review feedback weekly.
- Use the Phase 13 future roadmap only as a long-term architecture guardrail; it should not change normal MVP behavior.
- Track activation, weekly retention, memory usefulness, task acceptance, safety approvals, and cost per active user.
- Move to hosted beta only after the Phase 13 metrics are healthy.
