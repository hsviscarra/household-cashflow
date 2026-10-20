# Changelog

All notable changes per roadmap feature. Versions follow `v0.<feature>.0` until the app replaces
the Excel workbook.

## [Unreleased]

## [0.7.0] — F6 Banco Pichincha

### F6 — Spanish card statement with deferred purchases
- Banco Pichincha parser (docs/parsers.md): Spanish layout, both number formats, account-level
  lines (payments, interest, SOLCA, IVA withheld on digital services, early payoffs of deferred
  purchases), one block per card (replacement 6331 and original 2829), installments of deferred
  purchases; golden test on a synthetic statement; the real Jun 13 – Jul 12, 2026 statement ties
  out to 44.59 with every line categorized.
- Lines without a cardholder take the account owner as the person.
- ADR-004 and migration 0008: a month counts from the Excel history or from statements, never
  both; statement lines in history months are kept and listed with a note.
- Review page labels installments ("installment 2 of 6") and shows references on phones.

## [0.6.0] — F5 Bank of America

### F5 — Checking and savings from one combined statement
- Bank of America parser (docs/parsers.md): two accounts per statement, wrapped descriptions,
  deposits / withdrawals / card / checks / service fees sections; golden test on a synthetic
  statement; the real Aug 22 – Sep 22, 2026 statement ties out for both accounts.
- Staging handles statements that cover several accounts: each line goes to its account, each
  account ties out and is checked for continuity against its previous statement.
- The payer's label on a deposit (e.g. "August" on the September salary) is kept as
  `pay_reference` (migration 0007 adds it to `stg.stg_transaction`); the salary counts in the
  month it lands.
- On a bank account, money in without a rule is income (on a card it stays a refund).
- Review page shows each line's account on combined statements and the payer's label.

## [0.5.0] — F4 Capital One end to end

### F4 — Read, tie out, preview and approve a Capital One statement
- Migration 0006: `raw.statement_header`, `raw.raw_line`, `stg.import_batch`,
  `stg.stg_transaction`, `rej.rejected_line`; `core.transaction` gains `statement_file_id`,
  `raw_line_id`, `import_batch_id` and `post_date`.
- Capital One parser (docs/parsers.md): summary, lines per cardholder, fees and interest, year
  from the billing cycle; golden test on a synthetic statement; the real Sep 4 – Oct 3, 2026
  statement ties out to 3,932.84 (76 lines).
- Tie-out checks per card and for the statement, plus continuity with the previous statement.
  A statement that doesn't tie out, or has unreadable lines, can't be approved.
- Staging with merchant-rule categories, person and country per line; card payments are
  transfers, interest is a financial cost, credits on purchases are refunds. Identical lines on
  one statement are kept (each gets its own key); lines already loaded are flagged and skipped.
- Approve loads the batch into `core.transaction` in one database transaction and writes
  `audit.load_log`; Discard leaves core untouched. Re-reading a preview replaces it.
- Import page: "Read lines" per statement; review page with tie-out, totals by category, lines,
  rejects, Approve import / Discard. Transactions page (read-only) with a month picker.
- Overview: plan months give way to actual months as statements arrive.

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
