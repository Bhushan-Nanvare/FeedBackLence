# FeedbackLens

FeedbackLens collects user feedback from GitHub issues, CSV files and an embeddable widget, groups it into themes, spots problems that are growing and turns the biggest ones into tickets backed by real quotes.

> **Status:** Phase 0: project setup.

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, Alembic |
| Database and vectors | PostgreSQL + pgvector |
| Background jobs | Worker process backed by a Postgres job queue |
| AI | Gemini (tagging, embeddings, theme naming, answers) |
| CI | GitHub Actions |

## Project layout

```
backend/     FastAPI app, database models, migrations, tests
web/         Next.js frontend
docker-compose.yml   Local Postgres + pgvector
```

## Run locally

Requirements: Docker Desktop, Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 24.

**1. Start the database** (Postgres + pgvector on `localhost:5434`)

```bash
docker compose up -d
```

**2. Start the API** at http://localhost:8000 (interactive docs at `/docs`)

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

**3. Start the web app** at http://localhost:3000

```bash
cd web
npm install
npm run dev
```

The home page shows whether the API, database and pgvector are reachable.

Settings have working local defaults. To override them, copy `.env.example` to `.env` (backend) and `web/.env.example` to `web/.env.local` (frontend).

## Checks

Backend:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Frontend:

```bash
cd web
npm run lint
npm run build
```

The same checks run in GitHub Actions on every push and pull request.

## Roadmap

- [x] Phase 0: project setup
- [ ] Phase 1: GitHub import, AI tagging, feedback inbox
- [ ] Phase 2: theme grouping and dashboard
- [ ] Phase 3: ask questions with cited answers
- [ ] Phase 4: trend alerts, theme to ticket, CSV import
- [ ] Phase 5: workspaces and login, widget, cost tracking, evaluation in CI, deployment
