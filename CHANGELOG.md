# Changelog

All notable changes per roadmap feature. Versions follow `v0.<feature>.0` until the app replaces
the Excel workbook.

## [Unreleased]

## [0.4.0] — F3 Statement upload

### F3 — Upload, detect and keep statements
- Migration 0005: `raw.statement_file` (hash, source, status, last four digits found, period,
  storage key, who and when) and `raw.statement_file_account` (a BofA combined statement covers two
  accounts).
- Upload one or many PDFs (up to 50, 25 MB each) on the Import page or `POST /api/statements`.
  Each file is hashed; the same file is never saved twice, whatever its name.
- Detection by bank fingerprint (domains and legal names only), last four digits and statement
  period for Bank of America, Capital One, Banco Pichincha, Produbanco and Diners; unknown formats
  are kept for review. Password-protected or damaged PDFs are refused with a clear message.
- Account matching: last four digits first, then the bank's only account (replacement cards,
  Lauren's Produbanco); otherwise Hernan picks the account in the list.
- Files stored in Azure Blob Storage with the app's managed identity (`STORAGE_ACCOUNT_URL`), or a
  local folder (`STATEMENTS_DIR`, a Docker volume). `GET /api/statements/{id}/file` opens the PDF.

## [0.3.0] — F2 Excel history and first dashboard

### F2 — Excel history and Overview
- Migration 0004: `raw.excel_import` / `raw.excel_cell`, `core.transaction`, `core.budget`,
  `core.balance_snapshot`, `audit.load_log`; categories Health / Dad's Insurance, Savings & Debt /
  Loan Payments, Pets, Other Expenses; views `mart.v_monthly_cashflow` and `mart.v_category_month`.
- Workbook importer (ADR-002): August 2019 to June 2026 as monthly history, July to December 2026 as
  plan, 2026 side tables as raw cells and balance snapshots; reconciliation that names the rows each
  workbook TOTAL formula leaves out.
- Import page: preview (years, rows to confirm, TOTAL differences, balances) then Load history.
  CLI: `python -m app.cli.import_excel_history`.
- Overview page: the year in one sentence, money in / out / kept tiles, monthly columns with plan,
  running total since 2019, category table; light and dark, desktop and phone.
- API: `/api/history/excel/preview|load`, `/api/cashflow/monthly|categories|plan`.

## [0.2.0] — F1 reference data

### F1 — Accounts, categories and merchant rules
- Tables `core.account`, `core.category` (two levels, kind, color, fixed flag) and
  `core.merchant_rule` (contains / starts with / regex, priority) — migration 0002.
- Seed v1 from the project instructions (8 accounts with last four digits only, the category tree,
  50 merchant rules) — migration 0003, with a working downgrade.
- Rule engine: first active rule by priority wins; case and spacing ignored; invalid regex refused.
- API: list/create/update accounts and categories; CRUD for merchant rules; `/api/merchant-rules/test`.
- Settings page (Accounts, Categories, Merchant rules tabs) with inline edits, add forms and a rule
  tester, in the Mercado style, desktop and phone.
- Playwright end-to-end tests run in CI against the Docker image and SQL Server.

## [0.1.0] — 2026-10-19

### F0 — Walking skeleton and pipeline
- FastAPI app with `/api/health` (version, git SHA, database check) and `/api/me`.
- Email allow-list middleware for Container Apps sign-in.
- Alembic baseline creating the `raw`, `stg`, `rej`, `core`, `mart` and `audit` schemas.
- React shell with navigation to every planned page and a database status pill.
- Mercado design system (docs/design-system.md): color tokens with dark mode, Bricolage Grotesque + Figtree, category colors, button and behaviour rules; shell restyled with it.
- Single Docker image (API serves the web build); Docker Compose with SQL Server 2022.
- CI (lint, types, unit and integration tests, secret scan, image build) and deploy-on-merge to
  Azure Container Apps with smoke test and manual rollback.
- Azure Bicep (Container App, Azure SQL free offer with auto-pause, Blob, budget) and bootstrap script.
- Bootstrap registers resource providers, supports a separate SQL region and trusts GitHub's
  ID-based OIDC subject. Live in Azure South Central US.
