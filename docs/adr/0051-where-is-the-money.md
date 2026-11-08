# ADR-051: Where's the money

Status: accepted (0.65.0, Nov 2026)

## Context

Hernan: "It says we kept 38K but where is that money? The numbers don't match what I have in my
accounts." Kept is money in minus money out; nothing compared it with the balances, so errors in
classification stayed invisible.

## Decision

- `GET /api/reconcile?from=&to=` (months): money in, money out and kept for those months (the cash
  flow's own totals), against how each active account's balance changed from the last statement
  before the first month to the last statement by the end of the last month (cards: less owed counts
  as money kept). `gap = kept - balances_change`.
- With the gap, the usual causes and their amounts: balances missing at the start or end, statements
  missing at the end, transfers with one side loaded, money with people (transfers with a person),
  income that came by transfer (worth checking it isn't your own money or someone else's), and lines
  without a category. Each links to where it's fixed. Workbook months are flagged: they have no
  balances to compare.
- Cash flow shows a "Where's the money?" card for the year under the KPIs: kept, the change in
  balances, the gap or "They agree" (within $50), the causes, and the accounts on demand.

## Consequences

- A gap is something to investigate rather than a mystery; as statements are loaded and lines are
  fixed, it should shrink. Money sent to places the app doesn't follow (cash, an investment account
  without statements) stays in the gap unless it's categorized as savings.
