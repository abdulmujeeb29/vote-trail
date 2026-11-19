# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && apt-get update && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" DJANGO_SETTINGS_MODULE=votetrail.settings.prod \
    WORKER_HEARTBEAT_FILE=/app/data/.worker-heartbeat
COPY --chown=app:app . .
RUN SECRET_KEY=build PHONE_HMAC_KEY=build \
    FIELD_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/data && chown -R app:app /app/media /app/data /app/staticfiles
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fsS http://localhost:8000/healthz || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "scripts/start.sh"]
