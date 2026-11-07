# ADR-039: A monthly budget per group, with rollover

Status: accepted (0.55.0, Nov 2026)

## Context

Phase 2 of the improvement plan ("plan the month"). The app shows where money went but not what
was meant to be spent. `core.budget` holds the Excel plan rows by month, category and label
(ADR-010) and is history, not something a person edits.

## Decision

- **`core.budget_plan`** (migration 0032): one row per spending group and the month it starts,
  with an amount (≥ 0) and a rollover flag. The amount for a month is the row with the latest start
  on or before it, so "from this month on" is a single row; setting a budget from month X replaces
  that group's rows from X onwards. Amount 0 = no budget from then.
- Budgets are **per group** (Groceries, Dining…), not per subcategory: few enough to keep up with,
  and the same level as the Spending page.
- **Spent** comes from the Spending page's own view (`spending._by_category`), so the numbers
  match it.
- **Rollover**: for each earlier month since the group's first budget, budget minus spent is
  carried while that month's plan had rollover on; a month with it off starts the count again.
  Overspending carries as a negative.
- **Pace**: the share of the month gone (1 for a past month, 0 for a future one). A group is
  *over* past its available amount, *ahead of pace* when spent is more than 10% (and $10) above
  available × that share, otherwise *on track*.
- **Starting point**: each group's average of the 3 months before, rounded up to $10, offered
  per group and as "Start from the 3-month average" for every group without a budget.
- API: `GET /api/budget/{YYYY-MM}`, `PUT /api/budget/groups/{id}`,
  `POST /api/budget/{YYYY-MM}/start-from-average`. Page: Budget, under Plan.
- Deleting a category moves its budget rows with its lines (ADR-034); the target's own row for
  the same month wins.

## Consequences

- One budget for the household; the person switch doesn't split it.
- The forecast still uses the average of everyday spending (ADR-033), not the budget.
