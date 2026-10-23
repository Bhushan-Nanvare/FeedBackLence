# ============================================================================
# Makefile — common dev, test, build and deployment commands
#
# Usage:
#   make              — list all targets
#   make dev          — start local development (API + worker + web + db)
#   make test         — run backend tests
#   make build        — build production Docker images
#   make up           — start production stack
#   make down         — stop and remove all containers
#   make logs         — tail all container logs
#   make logs-api     — tail API container logs only
# ============================================================================

.DEFAULT_GOAL := help
.PHONY: help dev dev-db dev-api dev-worker dev-web \
        test lint \
        build build-api build-web \
        up down restart logs logs-api logs-worker logs-web \
        migrate shell-api shell-db \
        evals baseline

COMPOSE          := docker compose
COMPOSE_PROD     := docker compose -f docker-compose.production.yml
BACKEND_DIR      := backend
WEB_DIR          := web

# ─── help ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "FeedbackLens — available make targets"
	@echo "────────────────────────────────────────────────"
	@echo "  dev            Start local development environment"
	@echo "  dev-db         Start only the database"
	@echo "  dev-api        Start only the FastAPI backend (hot-reload)"
	@echo "  dev-worker     Start only the background worker"
	@echo "  dev-web        Start only the Next.js frontend"
	@echo ""
	@echo "  test           Run backend tests (pytest)"
	@echo "  lint           Run backend + frontend linters"
	@echo "  evals          Run the eval scorer against the demo workspace"
	@echo "  baseline       Save eval results as the new baseline"
	@echo ""
	@echo "  build          Build all production Docker images"
	@echo "  build-api      Build only the backend image"
	@echo "  build-web      Build only the frontend image"
	@echo ""
	@echo "  up             Start the production stack (detached)"
	@echo "  down           Stop and remove all containers and networks"
	@echo "  restart        Restart all production containers"
	@echo "  logs           Tail all production logs"
	@echo "  logs-api       Tail API logs only"
	@echo "  logs-worker    Tail worker logs only"
	@echo "  logs-web       Tail web logs only"
	@echo ""
	@echo "  migrate        Run Alembic migrations (via api container)"
	@echo "  shell-api      Open a shell inside the API container"
	@echo "  shell-db       Open a psql shell inside the DB container"
	@echo "────────────────────────────────────────────────"

# ─── local dev ───────────────────────────────────────────────────────────────

dev-db:
	$(COMPOSE) up -d

dev-api:
	cd $(BACKEND_DIR) && uv run uvicorn app.main:app --reload --port 8000

dev-worker:
	cd $(BACKEND_DIR) && uv run python -m app.worker

dev-web:
	cd $(WEB_DIR) && npm run dev

# Start database only, then print a reminder for the other services.
dev:
	$(COMPOSE) up -d
	@echo ""
	@echo "Database is up. Start the remaining services in separate terminals:"
	@echo "  make dev-api      (port 8000)"
	@echo "  make dev-worker"
	@echo "  make dev-web      (port 3000)"

# ─── testing & linting ───────────────────────────────────────────────────────

test:
	cd $(BACKEND_DIR) && uv run pytest -v

lint:
	cd $(BACKEND_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB_DIR) && npm run lint

# ─── evals ───────────────────────────────────────────────────────────────────

evals:
	cd $(BACKEND_DIR) && uv run python -m app.evals score --workspace demo

baseline:
	cd $(BACKEND_DIR) && uv run python -m app.evals score --workspace demo \
	  --save-baseline ../evals/baselines/demo.json
	@echo "Baseline saved. Commit evals/baselines/demo.json."

# ─── production build ────────────────────────────────────────────────────────

build-api:
	docker build -t feedbacklens-api backend/

build-web:
	docker build -t feedbacklens-web web/

build: build-api build-web

# ─── production stack ────────────────────────────────────────────────────────

up:
	$(COMPOSE_PROD) up -d

down:
	$(COMPOSE_PROD) down

restart:
	$(COMPOSE_PROD) restart

logs:
	$(COMPOSE_PROD) logs -f

logs-api:
	$(COMPOSE_PROD) logs -f api

logs-worker:
	$(COMPOSE_PROD) logs -f worker

logs-web:
	$(COMPOSE_PROD) logs -f web

# ─── maintenance ─────────────────────────────────────────────────────────────

migrate:
	$(COMPOSE_PROD) exec api alembic upgrade head

shell-api:
	$(COMPOSE_PROD) exec api /bin/sh

shell-db:
	$(COMPOSE_PROD) exec db psql -U feedbacklens -d feedbacklens
