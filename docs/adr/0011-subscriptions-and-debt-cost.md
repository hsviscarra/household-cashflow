# ADR-011: Subscriptions found by cadence; cost of debt from a mart view

- Status: accepted
- Date: 2026-10-27

## Context

F14 (issue #16) adds recurring charge detection, including weekly app billing, and interest and
fees per card, year to date. It is done when Capital One's year-to-date interest is shown and
the Pichincha app subscriptions are listed. Some app stores bill an app every week, so
monthly-only detection would miss them.

## Decision

- **Subscriptions are detected in Python** (`services/subscriptions.py`) because the rule is
  about the gaps between dates:
  - *Lines:* statement and manual expense lines of the last 400 days (split parents excluded),
    grouped by the review queue's merchant key on the description, so each app on the same store
    stays separate.
  - *Recurring:* a group repeats when every gap between charges is weekly (5–9 days), monthly
    (25–35), quarterly (80–100) or yearly (350–380), and every charge is within 25% of the median
    amount. The monthly cost is the median times 52/12, 1, 1/3 or 1/12.
  - *Possible:* a group in a Subscriptions & Software category that doesn't repeat (seen once,
    or at uneven gaps) is listed as possible, with no monthly cost added to the total.
  - *Active or stopped:* a subscription is active while its last charge is within one and a half
    intervals of the end of its card's latest approved statement. A card whose statements stop
    earlier can't tell, so it stays active.
  - *Not subscriptions:* Financial Costs (fees, interest, SOLCA, the tax on digital services)
    belong to the cost of debt, even when monthly.
- **Cost of debt is a SQL view.** `mart.v_debt_cost` (migration 0014) has interest and fees per
  account and month as positive amounts. Interest is the Credit Card Interest category (interest
  earned on a credit balance reduces it), and fees are the rest of Financial Costs. It follows the
  same Excel-or-statement and split rules as the other mart views. `GET /api/debt?year=` adds
  year to date, the last 12 months by month and category, and each card's latest statement
  balance as printed. Bank accounts have no debt balance.
- **Pages:** Subscriptions shows the monthly total, the weekly app billing and the charges behind
  each row. Debt & Net Worth shows interest and fees per account with a drill-down, and a chart of
  the last 12 months with its table.

## Consequences

- On the real data, Capital One's year-to-date interest comes from its statement's interest
  charge, and the Pichincha card shows its weekly app-store apps as active, with the one-off app
  charges as possible.
- Detection needs at least two charges: a new subscription shows as possible until its second
  charge. A price change above 25% splits the history; the latest charges still form a group.
- Net worth (balances of all accounts and the BIESS loan) is left for the projections and the
  monthly report (F15, F16).
