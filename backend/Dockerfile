# ============================================================================
# FeedbackLens Backend — production Dockerfile
#
# Multi-stage build:
#   1. "builder"  — installs Python deps with uv into a virtual env
#   2. "runtime"  — copies only the venv and app code into a slim image
#
# Usage:
#   docker build -t feedbacklens-api backend/
#   docker run -p 8000:8000 --env-file .env feedbacklens-api
# ============================================================================

# ---------- Stage 1: install dependencies with uv ----------
FROM python:3.11-slim AS builder

# uv is the fast Python package manager used throughout this project.
# Install it from the official standalone installer (no pip needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy only the dependency files first so Docker caches this layer.
# Changes to app code won't re-install dependencies.
COPY pyproject.toml uv.lock ./

# Create a virtual environment and install production dependencies.
# --frozen ensures the lock file is respected exactly.
# --no-dev skips test/dev dependencies (pytest, ruff).
RUN uv sync --frozen --no-dev

# ---------- Stage 2: production runtime ----------
FROM python:3.11-slim AS runtime

# Create a non-root user for security — never run containers as root.
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Copy the virtual environment from the builder stage.
COPY --from=builder /app/.venv /app/.venv

# Copy the application code and migrations.
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Copy the entrypoint script that runs migrations before starting.
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Make sure the venv's Python and packages are on the PATH.
ENV PATH="/app/.venv/bin:$PATH"
# Tell Python not to buffer stdout/stderr — logs appear immediately.
ENV PYTHONUNBUFFERED=1

# The API listens on port 8000.
EXPOSE 8000

# Switch to the non-root user.
USER app

# The entrypoint runs migrations then starts the server.
ENTRYPOINT ["./docker-entrypoint.sh"]

# Default command: start the API server.
# Override this with "worker" to run the background worker instead.
CMD ["api"]
