# ADR-001: Stack, hosting and repository layout

- Status: accepted
- Date: 2026-10-19

## Context

A two-person household needs to replace a multi-year Excel cash flow with an app that ingests PDF
statements from five institutions in two countries, reconciles them, and supports analysis.
Constraints: near-zero running cost, private financial data, maintainable by one data engineer
fluent in SQL Server and Python, with Claude doing most of the coding.

## Decision

- **Monorepo** `household-cashflow`: `api/` (FastAPI), `web/` (React), `infra/`, `sql/`, `mcp/`, `docs/`.
- **Database:** Azure SQL Database free offer (100,000 vCore-seconds and 32 GB a month, set to
  auto-pause when used up, never bill). SQL Server 2022 Developer in Docker locally. Six schemas:
  `raw`, `stg`, `rej`, `core`, `mart`, `audit`; the Alembic version table lives in `audit`.
- **API:** Python 3.12, FastAPI, SQLAlchemy 2, pyodbc with ODBC Driver 18, Alembic, uv.
- **Web:** React 18, TypeScript, Vite, TanStack Query, Tailwind. Routing uses React Router for the
  shell; TanStack Router can replace it later if typed routes become worth it.
- **One container:** FastAPI serves the built React app (same origin, no CORS, one Container App).
- **Hosting:** Azure Container Apps consumption (scale to zero, max 1 replica), Blob Storage for PDFs
  via managed identity, images on GitHub Container Registry, $1 budget alert.
- **Auth:** Container Apps built-in sign-in with Microsoft personal accounts, plus an email
  allow-list enforced in the API (`ALLOWED_EMAILS`). `/api/health` is open for probes and smoke tests.
- **CI/CD:** GitHub Actions. `ci.yml` on every PR and push; `deploy.yml` after CI succeeds on `main`,
  logging in to Azure with OIDC (no stored cloud secrets), then a smoke test on the new git SHA.
- **Migrations run at container start** (`alembic upgrade head`); safe with one replica.

## Consequences

- Cost stays near $0; a month that exhausts the free database allowance pauses the database until
  the next month instead of billing. Bulk historical loads run locally to save that allowance.
- SQL auth (admin login stored as a Container App secret) is used to start; moving to the app's
  managed identity as the database user is a later hardening step.
- The allow-list trusts the `X-MS-CLIENT-PRINCIPAL-NAME` header, which is only safe while
  Container Apps sign-in is enabled in front of the app. Never expose the app with sign-in disabled
  and real data loaded.
- Container App logs are not shipped to Log Analytics (to stay free); use `az containerapp logs show`.
