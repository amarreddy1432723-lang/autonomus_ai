# Self Hosting

## Local

Use Docker Compose for Postgres and Redis, then run backend services and frontend.

```powershell
docker compose up -d postgres redis
cd backend
python -m uvicorn services.agent.main:app --port 8003
cd ../frontend
npm run dev
```

## Required Environment

- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `NEXT_PUBLIC_AUTH_URL`
- `NEXT_PUBLIC_AGENT_URL`
- `NEXT_PUBLIC_GOALS_URL`

## Production Checklist

- Clerk configured
- Stripe webhook configured
- GitHub App configured
- Docker sandbox enabled
- Sentry and metrics enabled
- Backups configured
- Demo auth disabled
