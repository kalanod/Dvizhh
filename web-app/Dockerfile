# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM node:22-alpine AS frontend

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/ ./
# vite.config.ts кладёт сборку в ../src/dvizh_web/static
RUN npm run build

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY --from=frontend /app/src/dvizh_web/static ./src/dvizh_web/static
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /nonexistent --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app
EXPOSE 8002

CMD ["uvicorn", "dvizh_web.main:app", "--host", "0.0.0.0", "--port", "8002", "--proxy-headers"]
