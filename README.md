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
- Batch recovery runs with deterministic, configurable simulated outcomes and run history

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

## Step 3 AI Diagnosis

The agent provider is configured through environment variables:

```bash
LLM_PROVIDER=stub
```

The current `stub` provider returns deterministic structured JSON for local development and tests.
Provider-specific API keys should be added only inside provider-specific implementations, not in API
route handlers.

Analyze a detected recovery case:

```bash
curl -X POST http://localhost:8000/recovery/cases/{case_id}/analyze
```

Example response:

```json
{
  "decision_id": "decision-id",
  "recovery_case_id": "case-id",
  "status": "ACTION_REQUIRED",
  "decision": {
    "diagnosis": "temporary_payment_failure",
    "risk_level": "LOW",
    "recommended_action": "RETRY_PAYMENT",
    "delay_hours": 24,
    "confidence": 0.82,
    "reason": "The customer has a strong prior payment history and this looks recoverable."
  }
}
```

At this stage the agent only recommends an action. It does not execute payments, send emails, run
retries, or modify the database directly outside the backend service workflow.

## Step 4 Policy Engine and Simulated Execution

Execute the latest AI recommendation for a recovery case:

```bash
curl -X POST http://localhost:8000/recovery/cases/{case_id}/execute
```

Execution always follows the backend-controlled flow:

```text
AI decision -> policy engine -> bounded action executor -> outcome -> audit log
```

The policy engine enforces:

- maximum payment retries: 3
- minimum retry interval: 24 hours
- escalation after 3 failed attempts
- no automated `RETRY_PAYMENT` or `SEND_PAYMENT_LINK` for HIGH-risk cases unless explicitly allowed
- allowed actions: `RETRY_PAYMENT`, `SEND_PAYMENT_LINK`, `ESCALATE`, `STOP`

The action executor is simulated:

- `RETRY_PAYMENT` creates a payment attempt and simulates success or failure
- `SEND_PAYMENT_LINK` simulates a payment-link recovery success or failure
- `ESCALATE` marks the case as `ESCALATED`
- `STOP` marks the case as `STOPPED`

Successful simulated payment recovery sets `recovered_revenue` from the backend-owned payment
amount. The AI never determines recovered revenue and never executes actions directly.

Example approved execution response:

```json
{
  "executed": true,
  "idempotent": false,
  "action": "RETRY_PAYMENT",
  "status": "RECOVERED",
  "reason": "Simulated retry succeeded.",
  "recovered_revenue": "250.00",
  "payment_attempt_id": "attempt-id",
  "recovery_action_id": "action-id",
  "executed_at": "2026-09-05T09:00:00Z",
  "policy": {
    "allowed": true,
    "action": "RETRY_PAYMENT",
    "reason": "Retry limit has not been reached."
  }
}
```

## Step 5 Batch Recovery Simulation

Run all eligible recovery cases through the existing AI analysis, policy engine, bounded executor,
and audit services in one request:

```bash
curl -X POST http://localhost:8000/recovery/run \
  -H "Content-Type: application/json" \
  -d '{
    "retry_success_probability": 0.65,
    "payment_link_success_probability": 0.55,
    "simulation_seed": "hackathon-demo",
    "idempotency_key": "demo-run-001"
  }'
```

The probabilities are deterministic: a case, action, seed, and probability always produce the same
outcome. Set either probability to `1` to demonstrate guaranteed recovery or `0` for a guaranteed
failed outcome. Defaults can also be configured in `.env`:

```bash
SIMULATION_SEED=revive-demo
RETRY_SUCCESS_PROBABILITY=0.65
PAYMENT_LINK_SUCCESS_PROBABILITY=0.55
```

Example response:

```json
{
  "run_id": "7c0af9d1-58f0-48f7-a737-1be5be0e4c74",
  "cases_processed": 80,
  "actions_executed": 72,
  "recovered_cases": 45,
  "escalated_cases": 14,
  "stopped_cases": 0,
  "revenue_at_risk": "48500.00",
  "revenue_recovered": "31200.00",
  "recovery_rate": "0.6433"
}
```

`recovery_rate` is a backend-calculated ratio (`revenue_recovered / revenue_at_risk`), rounded to
four decimal places. Each run is persisted and may be reviewed with:

```bash
curl http://localhost:8000/recovery/runs
curl http://localhost:8000/dashboard/metrics
```

To demonstrate the full flow locally, run migrations, seed the data, start the API, then invoke
`POST /recovery/run` with a fixed seed. Repeating the same request with its `idempotency_key`
returns the original run without executing another action. A later request without that key only
processes cases that have not already reached an executed or policy-blocked action.

Example rejected execution response:

```json
{
  "executed": false,
  "idempotent": false,
  "action": "RETRY_PAYMENT",
  "status": "ACTION_REQUIRED",
  "reason": "Minimum retry interval has not elapsed.",
  "recovered_revenue": "0.00",
  "payment_attempt_id": null,
  "recovery_action_id": "blocked-action-id",
  "executed_at": null,
  "policy": {
    "allowed": false,
    "action": "RETRY_PAYMENT",
    "reason": "Minimum retry interval has not elapsed."
  }
}
```
