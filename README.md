# my-ai — Autonomous Personal AI Agent

`my-ai` is a multi-service autonomous personal AI agent for goals, planning, memory, approvals, live research, and guarded autonomous execution.

## Architecture

```text
                 Next.js Web Frontend
              local: http://localhost:3004
              default dev port: 3000
                         |
       ------------------------------------------------
       |                      |                       |
 Auth Service           Goals Service            Agent Service
 FastAPI :8001          FastAPI :8002            FastAPI :8003
 JWT + sessions         goals/tasks/plans        LangGraph brain
 integrations           approvals/schedules      memory/autonomy/news
       |                      |                       |
       -----------------------|------------------------
                              |
                    PostgreSQL 16 + pgvector
                         Redis 7 cache
```

## Current Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js App Router, React, TypeScript, CSS Modules |
| Server state | TanStack Query |
| Local state | Zustand |
| Backend | Python, FastAPI, Pydantic v2 |
| Agent orchestration | LangGraph |
| LLM providers | OpenAI-compatible router with local mock fallback |
| Embeddings | OpenAI `text-embedding-3-small` with mock fallback |
| Database | PostgreSQL 16 + pgvector |
| Cache / short-term memory | Redis 7 |
| ORM / migrations | SQLAlchemy 2 + Alembic |
| Security | JWT, bcrypt, encrypted integration tokens, security headers, append-only audit logs |
| Optional production adapters | Pinecone, Neo4j |

The machine-readable stack contract lives in [stack.json](./stack.json) and is exposed by every backend service at `/api/v1/stack`.
The implementation roadmap lives in [roadmap.json](./roadmap.json) and is exposed at `/api/v1/roadmap`.
The Phase 2 system architecture contract lives in [phase2.json](./phase2.json) and is exposed at `/api/v1/architecture/system`.
The Phase 3 AI architecture contract lives in [phase3.json](./phase3.json) and is exposed at `/api/v1/architecture/ai`.
The Phase 13 future roadmap lives in [phase13.json](./phase13.json) and is exposed at `/api/v1/future-roadmap`.
For compatibility, the same Phase 13 manifest is also exposed at `/api/v1/evaluation/status`.
Production launch checks are exposed at `/api/v1/production/readiness`.
Deployment steps live in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Ports

| Component | Port | Purpose |
|---|---:|---|
| Frontend | `3004` currently, `3000` default | Web app |
| Auth service | `8001` | Registration, login, sessions, integrations, security status |
| Goals service | `8002` | Goals, projects, tasks, approvals, schedules |
| Agent service | `8003` | Chat, memory, news, autonomy |
| PostgreSQL | `5432` | Relational data + pgvector |
| Redis | `6379` | Rate limiting and short-term memory |

## Local Setup

Start database services:

```bash
docker compose up -d
```

Install backend dependencies:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
```

Start backend services:

```bash
uvicorn services.auth.main:app --host 0.0.0.0 --port 8001 --reload
uvicorn services.goals.main:app --host 0.0.0.0 --port 8002 --reload
uvicorn services.agent.main:app --host 0.0.0.0 --port 8003 --reload
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev -- -p 3004
```

Open [http://localhost:3004](http://localhost:3004).

## Verification

```bash
python -m compileall backend\services
python -m pytest backend -q
cd frontend
npm run build
```

Useful runtime checks:

```bash
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/api/v1/health
curl http://localhost:8001/api/v1/stack
curl http://localhost:8001/api/v1/architecture/system
curl http://localhost:8001/api/v1/architecture/ai
curl http://localhost:8001/api/v1/roadmap
curl http://localhost:8001/api/v1/future-roadmap
curl http://localhost:8001/api/v1/evaluation/status
curl http://localhost:8001/api/v1/production/readiness
```

## Production Direction

Phase 11 defines the target production stack as AWS-first managed infrastructure: EKS, RDS/Aurora PostgreSQL, ElastiCache Redis, MSK Kafka, Kong Gateway, Cloudflare, Vault/KMS, OpenTelemetry, Prometheus, Grafana, Jaeger, Sentry, LangSmith, and security tooling such as Trivy, Semgrep, TruffleHog, Cosign, Falco, and Kyverno.

The current repo keeps local development small and reliable while preserving adapter boundaries for those production components.

## Implementation Roadmap

Phase 12 sequences the product into four release milestones:

| Release | Weeks | Goal |
|---|---:|---|
| MVP Local | 1-4 | Make the current local app complete, testable, and coherent for one user |
| Private Alpha | 5-8 | Validate daily usage with 5-10 trusted users |
| Beta | 9-16 | Add hosted reliability, observability, integrations, and operational runbooks |
| General Availability | 17-24 | Launch a stable product with support, rollback, and cost controls |

Manual actions before alpha/beta are tracked in [roadmap.json](./roadmap.json), including real LLM credentials, production secrets, hosting/domain selection, and alpha-user recruitment.

## Live Product Launch

Before inviting real users, configure production secrets outside the repository and verify:

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
OPENAI_API_KEY=<real-key>
SERPER_API_KEY=<real-key>
```

Then run:

```bash
python -m compileall backend\services
python -m pytest backend -q
npm run build
curl https://your-api-domain/api/v1/production/readiness
```

The readiness endpoint should have no critical failures before private alpha. Phase 13 is a future blueprint for the years 2-5 sovereign-agent direction: voice and ambient interfaces, decentralized identity, AI-to-AI protocols, portable memory standards, decentralized agent networks, and the cognitive-extension north star.
