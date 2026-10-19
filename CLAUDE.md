# Working on household-cashflow

Private household finance app. Read `README.md`, `docs/adr/`, `docs/definition-of-done.md` and
`docs/design-system.md` (Mercado: use its tokens and rules for every UI change) first.

## Rules
- Never commit real statements, workbooks, account numbers, cédulas or `.env`. Fixtures are synthetic.
- One roadmap feature at a time (F0 to F19); a feature is finished only when the Definition of Done holds.
- Branch `feat/Fxx-short-name`, Conventional Commit messages, draft PR early, Hernan merges.
- Keep changes minimal and targeted; no structural rewrites without asking.
- Ask before changing the database schema outside a migration planned for the current feature.

## SQL (T-SQL) conventions
- Keywords UPPERCASE; identifiers in brackets: `SELECT [t].[amount] FROM [core].[transaction] AS [t]`.
- Prefer sequential `#temp` table steps over long CTE chains.
- Data fixes: a SELECT preview first, then DML inside
  `BEGIN TRANSACTION; BEGIN TRY ... END TRY BEGIN CATCH ROLLBACK; THROW; END CATCH` with
  `-- COMMIT;` left commented until the preview is verified.
- Every schema change is an Alembic migration with a working `downgrade`.

## Commands
- API: `cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest --cov`
- Integration: `cd api && uv run pytest -m integration -o addopts=""` (SQL Server via `docker compose up -d sqlserver`)
- Web: `cd web && pnpm lint && pnpm typecheck && pnpm test && pnpm build`
- Everything: `docker compose up --build` → http://localhost:8000

## Money
- Amounts are USD (Ecuador is dollarized); never convert. Signed amounts: negative = outflow.
- Use `DECIMAL(19,4)` in SQL and `Decimal` in Python, never floats.
