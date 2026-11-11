# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY --from=dvizh_logging pyproject.toml /packages/dvizh-logging/
COPY --from=dvizh_logging src /packages/dvizh-logging/src

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
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
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app alembic ./alembic

USER app
EXPOSE 8003

CMD ["sh", "-c", "alembic upgrade head && exec python -m dvizh_auth.main"]

