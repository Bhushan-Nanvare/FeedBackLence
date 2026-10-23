#!/bin/sh
# ============================================================================
# docker-entrypoint.sh — runs database migrations, then starts the API or worker.
#
# Usage (set automatically by Dockerfile CMD, or override in docker-compose):
#   ./docker-entrypoint.sh api      — migrate + start uvicorn
#   ./docker-entrypoint.sh worker   — migrate + start the background worker
# ============================================================================
set -e

echo "Running database migrations..."
alembic upgrade head

MODE="${1:-api}"

case "$MODE" in
  api)
    echo "Starting FeedbackLens API on port 8000..."
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --workers 2 \
      --log-level info
    ;;
  worker)
    echo "Starting FeedbackLens background worker..."
    exec python -m app.worker
    ;;
  *)
    echo "Unknown mode: $MODE (expected 'api' or 'worker')"
    exit 1
    ;;
esac
