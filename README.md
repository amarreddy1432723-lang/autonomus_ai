# 🧠 my-ai — Autonomous Personal AI Agent

`my-ai` is an advanced multi-service **Autonomous Personal AI Agent** that dynamically decomposes long-term goals into critical path tasks, schedules cron triggers, manages memories semantically, and requests user approval for high-risk executions.

---

## 🏗️ System Architecture

The application is built using a modern decoupled monorepo structure:

```
               [ Next.js Web Frontend ] (Port 3000)
                         │
      ┌──────────────────┼──────────────────┐
      ▼ (Port 8001)      ▼ (Port 8002)      ▼ (Port 8006)
[ Auth Service ]   [ Goals Service ]   [ Agent Service ]
- JWT Validation   - Goal/Task CRUD    - LangGraph Brain
- Credentials      - Schedules DB      - Memory Cosine Search
- OAuth linking    - GraphQL Context   - Proactive Breifing
      │                  │                  │
      └──────────────────┼──────────────────┘
                         ▼
             [ PostgreSQL + pgvector ] (Port 5432)
```

---

## 🚦 Port Allocation

| Component | Port | Technology | Purpose |
|---|---|---|---|
| **Frontend** | `3000` | Next.js (React) | Dashboard, Chat, Kanban, Memory Views |
| **Auth Service** | `8001` | FastAPI (Python) | Credentials registration, Token verification |
| **Goals Service** | `8002` | FastAPI (Python) | Goal/Task decomposition, GraphQL, Scheduler |
| **Agent Service** | `8006` | FastAPI (Python) | AI Brain state machine, memory vector query |
| **Postgres** | `5432` | pgvector Image | Long-term memory store & relational state |

---

## 🛠️ Local Development Setup

### 1. Database & Cache
Launch the PostgreSQL database (pre-configured with `pgvector` support) and Redis using Docker:
```bash
docker-compose up -d
```

### 2. Backend Services
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create your local configuration:
   ```bash
   copy .env.example .env
   ```
5. Run database migrations:
   ```bash
   alembic upgrade head
   ```
6. Start the services locally:
   ```bash
   # Auth Service (Port 8001)
   uvicorn services.auth.main:app --port 8001 --reload

   # Goals Service (Port 8002)
   uvicorn services.goals.main:app --port 8002 --reload

   # Agent Service (Port 8006)
   uvicorn services.agent.main:app --port 8006 --reload
   ```

### 3. Frontend Web App
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
4. Open **[http://localhost:3000](http://localhost:3000)** in your browser!

---

## 🚀 Production Deployment (One-Click Railway)

This repository is optimized for deployment on **[Railway](https://railway.app)**:

### 1. Provision Services
Add these 5 services to your Railway project:
1. **Postgres** (Automatically supports `pgvector`)
2. **Auth Service**: Root directory = `backend`, Start Command = `uvicorn services.auth.main:app --host 0.0.0.0 --port $PORT`
3. **Goals Service**: Root directory = `backend`, Start Command = `uvicorn services.goals.main:app --host 0.0.0.0 --port $PORT`
4. **Agent Service**: Root directory = `backend`, Start Command = `uvicorn services.agent.main:app --host 0.0.0.0 --port $PORT`
5. **Frontend**: Root directory = `frontend`, Start Command = `npm run start`

### 2. Configure Environment Variables
* Set `DATABASE_URL` in the 3 backend services to `${{Postgres.DATABASE_URL}}`.
* Configure LLM key overrides (`GROQ_API_KEY`, `OPENAI_API_KEY`) inside the `agent` service variables.
* Link the frontend to the generated service domains:
  * `NEXT_PUBLIC_AUTH_URL` ➔ `https://your-auth-service.up.railway.app`
  * `NEXT_PUBLIC_GOALS_URL` ➔ `https://your-goals-service.up.railway.app`
  * `NEXT_PUBLIC_AGENT_URL` ➔ `https://your-agent-service.up.railway.app`
