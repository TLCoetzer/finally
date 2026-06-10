# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the Next.js static export
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /frontend

# Install dependencies first for better layer caching.
# Prefer a reproducible `npm ci` when a lockfile is present; fall back to
# `npm install` otherwise so the build still works without one.
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Build the static export (next.js `output: 'export'` -> frontend/out).
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python backend with uv, serving the API + static frontend
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS backend

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Use the system Python; don't let uv download an interpreter.
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Default DB path inside the container; the named volume mounts at /app/db.
    FINALLY_DB_PATH=/app/db/finally.db \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend

# Install dependencies from the committed lockfile (cached unless deps change).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy the backend source.
COPY backend/ ./

# Sync the project itself now that the source is present.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Place the frontend static export where FastAPI serves it.
COPY --from=frontend /frontend/out ./static

# The named volume mounts here; ensure the directory exists.
RUN mkdir -p /app/db

EXPOSE 8000

# Launched from /app/backend so the flat imports (`app:app`) resolve.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
