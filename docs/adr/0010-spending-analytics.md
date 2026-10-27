# ADR-010: Spending analytics from one mart view

- Status: accepted
- Date: 2026-10-27

## Context

F13 (issue #15) fills the Spending page: a drill-down, spending by person and country, fixed vs
variable, month over month (MoM), year over year (YoY) and top merchants. It is done when one
month's spending analysis is fully in the app. The plan calls for SQL to do the analysis so the
numbers are queryable outside the app (`mart.v_spending_by_person` in the original list).

## Decision

- **One line-level view instead of several aggregates.** `mart.v_spending_line` (migration
  0013) has one row per line that counts as spending: positive amount, group and category with
  the group's color, person (none → Joint), country (the line's, else its account's), the fixed
  flag, merchant (the normalized merchant, else the description), description and account.
  Every breakdown is a `GROUP BY` on it, so person, country and fixed share one definition, and
  the drill-down lists the rows behind a number.
- **Spending means the Overview's spending view:** types `expense` and `fee_interest` as
  positive, `refund` as negative. Transfers (card payments included), income, savings and debt
  payments are left out. The same two rules as `mart.v_monthly_cashflow` apply: the Excel
  history wins its months (ADR-004), and a split line counts through its parts (F9). Run against
  the real data, the page's total equals the Overview's spending for all 87 months.
- **Comparisons:** every group and category carries last month and the same month a year
  before. Categories with spending only in a compared month are kept (shown as −100%), so a
  stopped bill is visible.
- **Merchants** come from statement months only; the sheet has category rows, not merchants.
  They are grouped with the review queue's merchant key (F9: reference numbers and confirmation
  codes dropped), and refunds reduce them.
- **API:** `GET /api/spending?month=` returns the whole page (totals, groups with categories,
  person, country, fixed, top 10 merchants, the 12-month trend and the months available).
  `GET /api/spending/lines` returns the lines behind any number (group, category, merchant,
  person, country or fixed).

## Consequences

- No new tables. The view can be queried from outside the app (and by the MCP server, F18).
- A big "Uncategorized" group is a prompt to finish Review; the page shows it like any group.
