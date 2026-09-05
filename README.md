# FluxPay

FluxPay is an AI-guided revenue-recovery MVP. It tracks failed payments, creates recovery cases, recommends actions, and shows recovery activity in a React dashboard.

## Stack

- Frontend: React, TypeScript, and Vite
- API: FastAPI and SQLAlchemy
- Database: PostgreSQL 16
- Migrations: Alembic
- Local containers: Docker Compose

## Run locally

### Prerequisites

- Docker Desktop with Docker Compose
- Node.js 20+ (for the frontend)

### 1. Configure environment variables

From the repository root:

```bash
cp .env.example .env
```

Set strong, unique values for `POSTGRES_PASSWORD` before deploying anywhere other than your computer. The `DATABASE_URL` in `.env` is for host-side commands; Docker overrides it internally so the backend uses the `postgres` service.

### 2. Start the API and database

```bash
docker compose up -d --build
```

Check that both services are running:

```bash
docker compose ps
```

### 3. Run database migrations

Run migrations from the Docker network. This avoids conflicts with any PostgreSQL instance installed directly on the host.

```bash
docker compose run --rm backend alembic upgrade head
```

### 4. Seed demo data

```bash
docker compose run --rm backend python -m app.scripts.seed
```

The seed script recreates its demo records: 10 customers and 80 recovery cases, including payments, failed attempts, AI decisions, actions, and audit logs.

### 5. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the app at <http://localhost:5173>. API documentation is at <http://localhost:8000/docs>; health endpoints are `/health` and `/health/db`.

## Operations

View logs:

```bash
docker compose logs -f backend
docker compose logs -f postgres
```

Stop services without deleting database data:

```bash
docker compose down
```

For a fresh local database only (this deletes the database volume):

```bash
docker compose down -v
```
