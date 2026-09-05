# Revive - AI Revenue Recovery Agent

Revive is a hackathon MVP for detecting failed payments, preparing recovery cases, and laying the foundation for an AI-guided revenue recovery workflow.

This milestone includes:

- React + TypeScript + Vite frontend shell
- FastAPI backend
- PostgreSQL via Docker Compose
- SQLAlchemy models for customers, payments, attempts, recovery cases, actions, agent decisions, and audit logs
- Alembic migrations
- Deterministic seed data with 80 failed payment recovery cases
- Health-check endpoint
- Clean AI provider boundary for later structured decisions

## Requirements

- Docker and Docker Compose
- Python 3.11+
- Node.js 20+

## Local Setup

Copy the example environment file:

```bash
cp .env.example .env
```

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Set up the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

In a second terminal, set up the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- Database health: http://localhost:8000/health/db
- API docs: http://localhost:8000/docs

## Docker Backend Option

After creating `.env`, you can also run PostgreSQL and the backend together:

```bash
docker compose up --build
```

Then run migrations and seed data from the host or inside the backend container:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed
```

## Architecture Boundary

The LLM integration is intentionally isolated under `backend/app/services/ai`.

Future recovery execution should follow this flow:

```text
LLM -> structured decision -> backend validation -> policy engine -> action executor
```

The LLM must not write to the database or execute actions directly. Backend code owns policy enforcement, financial calculations, persistence, and action execution.

## Step 2 Endpoints

Mark a payment as failed and create a recovery case:

```bash
curl -X POST http://localhost:8000/payments/{payment_id}/fail \
  -H "Content-Type: application/json" \
  -d '{"failure_reason":"INSUFFICIENT_FUNDS"}'
```

List detected recovery cases:

```bash
curl http://localhost:8000/recovery/cases
```

Dashboard metrics:

```bash
curl http://localhost:8000/dashboard/metrics
```

Database health:

```bash
curl http://localhost:8000/health/db
```
