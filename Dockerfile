# One image: FastAPI serves the API and the built React app from the same origin.

# ---- web build ----
FROM node:22-alpine AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# ---- api runtime ----
FROM python:3.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Microsoft ODBC Driver 18 for SQL Server (pyodbc needs it); amd64 in Azure/CI, arm64 on Apple Silicon.
# Tesseract reads statements that arrive as pictures (Pacificard, ADR-005).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc tesseract-ocr \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/app ./app
COPY api/migrations ./migrations
COPY api/alembic.ini ./
COPY --from=web /web/dist ./web_dist
COPY infra/docker/entrypoint.sh /entrypoint.sh

ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA \
    PATH="/app/.venv/bin:$PATH" \
    WEB_DIST_DIR=/app/web_dist \
    STATEMENTS_DIR=/data/statements

# Local statement storage (a volume in compose; Azure uses Blob Storage instead).
RUN useradd --create-home --uid 10001 app && chmod +x /entrypoint.sh \
 && mkdir -p /data/statements && chown -R app:app /data
USER app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
