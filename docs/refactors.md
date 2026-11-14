# Proposed refactors

Shortfalls found in existing code against the code-quality standard in the Definition of Done.
Per the scope rule they are logged here and not rewritten in place; each ships as its own
reviewed change. Ordered by what the user would feel first.

| # | Where | Shortfall | Proposed change |
|---|-------|-----------|-----------------|
| 1 | `services/todo.py` | Done in 0.95.0 (ADR-086): the merchant key is stored and the scans behind Suggestions are SQL. Still open: `classify.uncategorized` and `status.month_status` are rebuilt for every To do; small today, worth a look if months of history grow. | Measure again when the list feels slow; cache month status per request. |
| 2 | `services/gastos.py` | Performance. `rows()` rebuilds the year's invoices, rules, paying lines and product shares on every call, and one invoice choice calls it twice (choice, then the row to return). | Build one row by id for the choice endpoint; share one `rows()` per request between summary and list. |
| 3 | `services/status`, `services/recurring` | Done in 0.112.0 (ADR-103): each is a package of modules by reason to change, with the same public functions. | |
| 4 | `web/src/pages/Settings.tsx` (1,515), `Recurring.tsx` (1,254), `Transactions.tsx` (1,092), `api.ts` (2,012) | Single responsibility, readability. | One file per tab or dialog; `api.ts` split by feature (types generated from the OpenAPI spec, as the plan intended). |
| 5 | routers | Done in 0.111.0 (ADR-102): one `app.auth.current_user` for every router. | |
| 6 | `routers/*` | Layering. Some routers still orchestrate (statement approval follow-ups, as bank sync did before ADR-085). | Move follow-ups into services, as `services/refresh.py` does for the sync. |
| 7 | Outside calls | Done. 0.111.0: named errors and `outside.retry` for the bank sync, backups, statement text and health. The Claude calls already name `anthropic.APIError` and use the SDK's own retries and timeouts. Three places catch everything on purpose and log it (alerts, the two autopilots): a helper that runs after a load must not fail the load. | |
| 8 | `services/transfers.py` ↔ `classify.py`; `models.py` | Dependency direction. Mostly done in 0.112.0 (ADR-103): the safe-rule check and the review priority live in the rule engine, and the imports inside functions are gone. Two remain on purpose: transfers and classify each need the other (a matched transfer may be split; an edited line may be re-matched), and the models register the flush listeners that call `payday` and `rules`. | Move `split` and `Part` to their own module if a third user appears. |
| 9 | `web/src/pages/Todo.tsx` and others | Magic numbers. Rule priority `50` typed in the web app; thresholds inline in services (`MIN_TIMES`, `PURPOSE_DAYS`, `FRESH_DAYS`). | The API chooses the default priority; household thresholds move to `app.config` settings. |
| 10 | `services/bank_sync.py`, `services/status.py` | Typed boundaries. The sync log's summary is a JSON string read back as raw dicts. | A Pydantic model for the summary, validated on read. |
| 11 | `web/src/pages/Transactions.tsx` (bulk actions) | Performance. "Categorize as" and "Whose" for ticked lines send one request per line (ADR-093, ADR-095). | A `PATCH /api/transactions` that takes ids and one change, in one transaction, still writing one history entry per line. Only if ticking hundreds becomes normal. |
| 12 | `services/subscriptions.py` | Detection. Charges are grouped by merchant whatever card paid, so the same service on two cards reads as one uneven subscription and isn't flagged as a duplicate (ADR-097). | Group by merchant and card before testing the cadence; then two steady groups of one merchant are a duplicate to show. |
| 13 | `web/src/pages/NetWorthAhead.tsx`, `Explore.tsx` | Single responsibility. Saving's debts are their own file since 0.111.0; these two are under the 400-line limit but hold sections, forms and helpers in one file. | One file per section, the page only composing them. |
| 14 | `services/savings.py`, `outlook.py`, `explore.py` | Dependency inversion. They call other service modules and the session directly, as every service here does; nothing is injected but the Claude caller in `ask.py`. | If a second data source ever appears, put reads behind a small Protocol per service, as `ask.Caller` does. Not worth it before then (YAGNI). |
| 15 | Long functions | Done in 0.114.0 (ADR-105): the last 12 (the parsers' `parse`, `stage.parse_statement`, `excel_history._parse_sheet` and `_checks`) are split. No function carries a `C901`/`PLR0915` exception any more. | |
| 16 | 23 web files in `BASELINE` (`web/eslint.config.js`) | Over 400 lines (ADR-102); the largest are item 4. | Split by section or tab; take the file off the list with each. |
