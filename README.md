# Household Cash Flow

Private web app that replaces the family Cash Flow workbook. Hernan and Lauren upload bank and
credit card statements (Bank of America, Capital One, Banco Pichincha, Produbanco, Diners); the app
parses them, ties each statement out to its own totals, and only loads an approved batch. Dashboards
show the monthly cash flow, spending by category, recurring items, subscriptions, cost of debt and
projections.

- **Architecture and plan:** the "Cash Flow App — Architecture & Plan" doc (Claude Project
  "Personal Accountant"), summarized in [`docs/adr/0001-stack.md`](docs/adr/0001-stack.md).
- **Roadmap:** features F0 to F19, built one at a time; each one meets the
  [Definition of Done](docs/definition-of-done.md) before the next starts.

## Stack

FastAPI (Python 3.12) · Azure SQL Database (SQL Server 2022 locally) · Alembic · React + TypeScript
(Vite, TanStack Query, Tailwind) · Docker · GitHub Actions · Azure Container Apps (free tiers).

## Run locally

Requires Docker.

```bash
cp .env.example .env            # set MSSQL_SA_PASSWORD
docker compose up --build       # http://localhost:8000
docker compose --profile dev up # also starts Vite with hot reload on http://localhost:5173
```

On start the API creates the `cashflow` database (local only), applies migrations and serves the
built web app. `GET /api/health` reports the version and whether the database answers.

### Without Docker for the app (SQL Server still in Docker)

```bash
docker compose up -d sqlserver
cd api && uv sync && uv run python -m app.db.ensure_database && uv run alembic upgrade head
uv run uvicorn app.main:app --reload            # API on :8000
cd ../web && pnpm install && pnpm dev           # UI on :5173, proxies /api to :8000
```

## Checks (the same ones CI runs)

```bash
cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest --cov
cd api && uv run pytest -m integration -o addopts=""   # needs SQL Server + DATABASE_URL
cd web && pnpm lint && pnpm typecheck && pnpm test && pnpm build
# End-to-end (needs the app on :8000, e.g. docker compose up):
cd web && pnpm exec playwright install chromium && pnpm e2e
pre-commit run --all-files
```

## Deploy

- **One-time setup:** [`infra/azure/bootstrap.sh`](infra/azure/bootstrap.sh) creates the Azure
  resources (Container App, Azure SQL free offer with auto-pause, storage, $1 budget alert), the
  Microsoft sign-in, and the GitHub OIDC identity used by deploys.
- **Every merge to `main`:** CI passes → `deploy.yml` builds the image to GHCR, rolls the Container
  App and smoke-tests `/api/health` for the new git SHA.
- **Rollback:** run the Deploy workflow manually with the previous image tag (git SHA).

## Data safety

Statements, workbooks and `.env` are git-ignored and blocked by a pre-commit hook; gitleaks runs in
pre-commit and CI. Tests use synthetic fixtures only.
