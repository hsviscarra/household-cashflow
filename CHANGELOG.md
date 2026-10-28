# Changelog

All notable changes per roadmap feature. Versions follow `v0.<feature>.0` until the app replaces
the Excel workbook.

## [Unreleased]

## [0.17.0] — F15 Projections

### F15 — The next 3 months on screen
- Projections page (ADR-013): the next three months in cash terms, built from:
  - income and fixed outflows from the recurring items;
  - variable spending (the average of the last three months' bank spending no recurring item
    paid);
  - purchase installments.
- For each month, net and cash at month end, starting from the bank balances on the latest
  statements, and each month's items by day.
- Cash day by day up to the end of the third month: the lowest balance and the payday after it,
  with a warning when cash goes below zero, and a chart with its table.
- Alerts for spending groups more than 30% above their previous three-month average, with a
  link to Spending.
- `GET /api/projections`. No schema change.

### Fixes
- Dates entered on the balance sheet (and the Recurring page's default month) used the UTC date,
  which is already tomorrow in Quito after 7 pm; they now use the local date.

## [0.16.0] — F14 Balance sheet

### F14 — What the household owns and owes (Debt & Net Worth)
- Balance sheet (ADR-012) at the top of Debt & Net Worth: net worth, what you own, what you
  owe and what is still to pay on purchases, then cards grouped by kind (property, vehicles,
  investments, cash, purchases in progress; loans, credit cards, owed to people), and net worth
  over the last 24 months with its table.
- Bank and card balances from each latest statement. Holdings (`core.holding`, migration 0015)
  valued by dated snapshots: the workbook's debts and savings become holdings, and anything else
  is added on the page with its value and the date it was bought. Update value, history, edit,
  pause, remove.
- A purchase in progress (the new house's down payment) shows paid so far, installments left
  and the amount financed at delivery. A loan shows its monthly payment from Recurring.
- `GET /api/networth`, `POST/PATCH/DELETE /api/holdings`, values per holding.

## [0.15.0] — F14 Subscriptions and cost of debt

### F14 — Capital One YTD interest shown; Pichincha app subscriptions listed
- Subscriptions page (ADR-011): charges that repeat weekly, monthly, quarterly or yearly with a
  similar amount, found in the statements (weekly app billing included). Each shows its card,
  typical amount, monthly and yearly cost, last and next charge, and Active or Stopped?; one-off
  charges in a subscription category are listed as possible.
- Debt & Net Worth page: interest and fees per account for the year and the last 12 months, by
  kind and by month, each card's latest statement balance, and a chart with its table.
- `mart.v_debt_cost` (migration 0014). `GET /api/subscriptions`, `GET /api/debt`.

## [0.14.0] — F13 Spending analytics

### F13 — One month's spending analysis fully in the app
- Spending page (ADR-010): a headline with the month's spending against last month and the same
  month last year, then:
  - categories grouped with their colors, each with MoM and YoY, expanding to subcategories and
    the lines behind them;
  - by person, by country, and fixed vs variable, each clickable to its lines;
  - the top 10 merchants of statement months;
  - the last 12 months as a chart with a table of the same numbers.
- `mart.v_spending_line` (migration 0013): one row per spending line. The page's total equals
  the Overview's spending view for every month.
- `GET /api/spending`, `GET /api/spending/lines`.

## [0.13.0] — F12 Month status

### F12 — Each month shows complete or what is missing
- Data Status page (ADR-009): every month from the end of the Cash Flow sheet to today is
  Complete or lists what is missing, each item with a link to fix it.
  - Statements: the days no approved statement covers, per active account (card statements
    counted by day).
  - Imports waiting for approval or failing their tie-out.
  - Lines without a category, transfers without their other side.
  - Recurring items not paid yet.
  - Balance breaks between consecutive statements.
- Coverage table (accounts × months: full, part with days, none) and the load log.
- `GET /api/status`. No schema change.

### Fixes
- Recurring "Change from month X" failed on SQL Server (`is_override IS 0` is not valid T-SQL);
  it now filters with `= 0`. A unit test guards against boolean `IS` comparisons.

## [0.12.0] — F11 Recurring entries

### F11 — The 2026 workbook rows reproduced in the month grid
- Recurring page (ADR-008): rows grouped as Income and Expenses like the sheet, January to
  December, paid amounts (linked lines) or expected ones, with Money in, Money out and Left.
  Select a cell to set this month only, change from this month on, skip it, or link and unlink
  lines; select an item to edit, pause or remove its template.
- Templates with an amount history; Generate a month; Copy a month forward or to a range.
- "From the 2026 sheet" turns the workbook's rows into templates and fills the year: past months
  linked to the history lines, the rest from the sheet's plan.
- Matching to statement lines by category, account (or the transfer's other side) and description
  pattern within a tolerance; two lines can pay one item. Runs after approve and reload.
- The Overview's plan uses the recurring entries for months that have them.
- Migration 0012 (`recurring_template`, `recurring_amount`, `recurring_entry`,
  `transaction.recurring_entry_id`) with a working downgrade.

### Tests
- The e2e spec for the Review page waits for its queue before checking it (0.11.0 follow-up).

## [0.11.0] — F10 Transfers and two views

### F10 — Card payments left out of spending and shown in the cash view
- Transfer matching across accounts (ADR-007): opposite, equal amounts on two accounts within 5
  days are linked (`transfer_group_id`) and categorized *Card Payment* or *Between Own Accounts*;
  runs after approve, after resolving or editing a line into a transfer, and on demand. A category
  chosen by hand is never overridden; a wrong pair is unlinked in one click; every change logged.
- New `mart.v_monthly_cash` and `GET /api/cashflow/monthly?view=cash`: bank accounts only, card
  payments counted as cash out, moves between own accounts left out.
- Overview: Spending view / Cash view toggle. Transactions: a matched line names the other
  account and date. Review: "Transfers without their other side", with "Match transfers again".
- Migration 0011 (column, index, `category_source = 'match'`, the view) with a working downgrade.

## [0.10.3] — Claude suggestions answer with ids

- The log showed the real cause: a merchant description with double quotes (a Zelle payment
  "FOR \"… ORDER\";") came back unescaped inside Claude's JSON, so the whole answer failed. Claude
  now answers with short ids for merchants and categories ("m1", "c3"), mapped back on the server,
  so no description or category name is ever repeated inside the JSON.

## [0.10.2] — Claude suggestions, tolerant reading

- Claude's reply finished normally but wasn't in the exact expected shape, so it was rejected. The
  reply is now read even with a code fence or words around the JSON, a bare list, or
  "merchant"/"category" field names; one bad item is skipped instead of failing all; category
  names match regardless of spacing and case. An unreadable reply logs the parse error and its
  first 300 characters.

## [0.10.1] — Claude suggestions fix

- "Claude's answer could not be read": Claude Haiku 5.5 thinks before answering and that counts
  toward max_tokens, so the JSON was cut off. Suggestions now run at low effort with a 16,000-token
  limit and at most 20 merchants per request; a cut-off or declined answer is reported as such.

## [0.10.0] — F9 Classification

### F9 — Unknown merchants of a month resolved in one screen
- Review page: uncategorized lines grouped by merchant (reference numbers and confirmation codes
  ignored), biggest amounts first; choose a category once, optionally save a rule (pattern, match,
  amount range) that is applied right away to every other uncategorized line it matches.
- Claude suggestions with confidence (ADR-006): `claude-haiku-5-5`, JSON-schema answers limited to
  Hernan's categories, only description/amount/date/bank sent, nothing applied until accepted.
  `ANTHROPIC_API_KEY` passed by Compose, Bicep and the bootstrap.
- Transactions page: edit a line's category and note (with Undo), split a line across categories
  (the parts must add up; the views count the parts instead of the line), each line's history.
- Merchant rules can carry an amount range; the Produbanco IESS split (empleada IESS vs BIESS)
  is now two editable rules instead of code (seed v4). The rule tester takes an amount.
- `audit.change_log` records every edit with old and new values and who made it; lines record
  where their category came from (rule, statement section, chosen, suggestion, workbook, split).
- Migration 0010 (rule ranges, splits, category source, change log, suggestions; views skip a
  split line; downgrade refuses while splits exist). Deleting a rule keeps the categories it gave.

## [0.9.2] — OCR fallback for every bank

- A statement PDF without text (a scan) is recognized and read with OCR for any bank, then goes to
  that bank's parser and tie-out (ADR-005 update). Scans of all five text formats tie out.
- OCR adapts to the picture's resolution, keeps signs, "$" and the decimal mark of each amount, and
  rejects impossible amounts ("00,00").
- Diners matches labels without accents; Produbanco recovers a lost sign from the running balance;
  Pacificard settles a tie between two printings of a total with the one the lines balance with.

## [0.9.1] — F8b Pacificard

### F8b — Banco del Pacífico Mastercard, read from a screenshot
- Pacificard statements are pictures (a saved web page with a "COPIA" watermark): they are read
  with Tesseract OCR inside the app (ADR-005), amounts and dates re-read digits-only and decided by
  majority; the parser handles OCR noise and the tie-out blocks any misread digit. The real Apr –
  Sep 2026 statements tie out and chain month to month.
- New account "Pacificard Mastercard Black" (Lauren's additional card goes to Lauren) and rules for
  SOLCA, IVA on digital services, credit-life insurance and AWS (migration 0009, seed v3);
  `raw.statement_file` accepts the new source.
- The Import page explains the wait while a picture is read.
- `tesseract-ocr` in the Docker image and CI.

## [0.9.0] — F8 Diners Club

### F8 — Diners statements, main and additional cards
- Diners Club parser (docs/parsers.md) for Hernan's and Lauren's statements: one block per card,
  deferred purchases (installment billed on the closing date, remaining balance checked),
  interest, late and collection charges, SOLCA, payments across a page break; golden test with a
  main and an additional card; the real Jul, Aug and Oct 2026 statements tie out.
- Upload matches a Diners statement to Hernan's or Lauren's account by the main cardholder's name
  ("Matched by the cardholder's name" on the Import page); detection now reads Diners card digits
  and the period.
- Continuity compares only with an adjacent statement, so a missing month no longer blocks a
  correct statement.
- Reading an unrecognized format says so plainly.

## [0.8.0] — F7 Produbanco

### F7 — Savings accounts with a running balance
- Produbanco parser (docs/parsers.md) for Hernan's and Lauren's accounts: Spanish month names,
  signed amounts, `#` IVA marks removed; ties out opening + lines = closing and checks every
  printed running balance; golden test on a synthetic statement; the real Jun, Jul and Aug 2026
  statements tie out (Jul 297.71 → 6.73) and chain month to month.
- Fees (`TARIFA`), card payments and capitalized interest are categorized by section.
- The two IESS payments that print the same are split by amount: the empleada's IESS and the
  BIESS house loan.

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
