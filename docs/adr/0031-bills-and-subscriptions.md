# ADR-031: Bills & subscriptions, one page, any schedule

Status: accepted (0.47.0, Nov 2026)

## Context

The redesign's seventh PR (ADR-025). Recurring items were monthly only, with no day, so a
yearly insurance, a quarterly tax or the 18 house installments didn't fit, and nothing said
what was late. Subscriptions found in the statements lived on a separate page.

## Decision

- **Schedule** (migration 0030): `core.recurring_template.every_months` (1 monthly, 2, 3, 4,
  6 or 12; 0 once, only its first month; existing rows are monthly) and `due_day` (1-31,
  optional). An item is due in a month when it's active, inside its first and last month, and
  the months since its first divide by `every_months`. Generate, the year grid and the
  forecast all follow it. Installments use the last month ("18 payments from Sep 2026" ends
  Feb 2028), and the page counts the payments left.
- **`GET /api/recurring/bills?month`**: each item due that month with its group, account,
  schedule, expected and paid amounts, status (**paid** when a line matched it; **late** when
  its day, or the month, passed without one; **due**; **skipped**), the day (set, or the usual
  day of the lines that paid it in the last year), the average paid over the three months
  before, payments left, and its latest price change within six months.
- **One page, five views** at `/recurring` ("Bills & subscriptions"): **Calendar** (each item
  on its day, Monday first; a list on phones; items without a day underneath), **By group**
  (group totals that open to their items), **Price changes**, **Year grid** (the existing
  editor) and **Found in statements** (the subscriptions page). Tiles: committed this month,
  paid so far, late, subscriptions per year. **Add a bill** has Repeats, On day and Last month.
- `/subscriptions` still works and opens the last view; the sidebar lists only Bills &
  subscriptions.

## Consequences

- Twice-a-month or every-two-weeks items (the empleada's two payments) stay two items, one per
  payment day, since entries are per month.
- Entries already generated in months a new schedule skips stay until removed on the grid.
