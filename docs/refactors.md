# Proposed refactors

Shortfalls found in existing code against the code-quality standard in the Definition of Done.
Per the scope rule they are logged here and not rewritten in place; each ships as its own
reviewed change. Ordered by what the user would feel first.

| # | Where | Shortfall | Proposed change |
|---|-------|-----------|-----------------|
| 1 | `services/todo.py` | Done in 0.95.0 (ADR-086): the merchant key is stored and the scans behind Suggestions are SQL. Still open: `classify.uncategorized` and `status.month_status` are rebuilt for every To do; small today, worth a look if months of history grow. | Measure again when the list feels slow; cache month status per request. |
| 2 | `services/gastos.py` | Performance. `rows()` rebuilds the year's invoices, rules, paying lines and product shares on every call, and one invoice choice calls it twice (choice, then the row to return). | Build one row by id for the choice endpoint; share one `rows()` per request between summary and list. |
| 3 | `services/status.py` (851 lines), `services/recurring.py` (1,118) | Single responsibility. Status mixes coverage, sources, timeline, bills, balance breaks and the load log; recurring mixes templates, entries, matching, the grid and bills. | Split by reason to change: `status/coverage.py`, `status/items.py`, `recurring/bills.py`, `recurring/matching.py`, keeping the public functions. |
| 4 | `web/src/pages/Settings.tsx` (1,515), `Recurring.tsx` (1,254), `Transactions.tsx` (1,092), `api.ts` (2,012) | Single responsibility, readability. | One file per tab or dialog; `api.ts` split by feature (types generated from the OpenAPI spec, as the plan intended). |
| 5 | 14 routers | DRY. Each defines its own `_user(request)`. | One `Depends(current_user)` in `app.auth`. |
| 6 | `routers/*` | Layering. Some routers still orchestrate (statement approval follow-ups, as bank sync did before ADR-085). | Move follow-ups into services, as `services/refresh.py` does for the sync. |
| 7 | `services/bank_sync.py`, others (15 places) | Error handling. `except Exception` around network calls; no retry with backoff on SimpleFIN or the Claude API. | Catch the specific client errors; one small retry helper with a timeout and backoff for outside calls. |
| 8 | `services/rules_suggest.py`, `classify.py`, `todo.py` | Dependency direction. They import each other, worked around with imports inside functions. | `rule_ok` and the generic-words list belong with the rule engine; then the cycle goes away. |
| 9 | `web/src/pages/Todo.tsx` and others | Magic numbers. Rule priority `50` typed in the web app; thresholds inline in services (`MIN_TIMES`, `PURPOSE_DAYS`, `FRESH_DAYS`). | The API chooses the default priority; household thresholds move to `app.config` settings. |
| 10 | `services/bank_sync.py`, `services/status.py` | Typed boundaries. The sync log's summary is a JSON string read back as raw dicts. | A Pydantic model for the summary, validated on read. |
| 11 | `web/src/pages/Transactions.tsx` (bulk actions) | Performance. "Categorize as" and "Whose" for ticked lines send one request per line (ADR-093, ADR-095). | A `PATCH /api/transactions` that takes ids and one change, in one transaction, still writing one history entry per line. Only if ticking hundreds becomes normal. |
