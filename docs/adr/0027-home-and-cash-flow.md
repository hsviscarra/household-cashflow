# ADR-027: Home as a dashboard, and a Cash flow page with drill-down

Status: accepted (0.43.0, Nov 2026)

## Context

The redesign's third PR (ADR-025). Home was the year history: the right numbers, but nothing
said what needed attention, what was coming, or why a month was different. The approved mockups
split it: Home answers "what do I need to know now", and a new Cash flow page answers "where did
the money come from and go, and why did it change".

## Decision

- **Cash flow** (`/cashflow`, in Analyze): twelve months of money in and out (pick a month), the
  month as a **Sankey** (money in by category on the left, money out by group on the right,
  savings and payments by category, "Left over" or "From savings"), and **why it changed**: a
  waterfall from last month's total to this month's through the five biggest changes, with a
  table. Every band and row drills down **group → category → merchant → lines**; the drill
  path sits in the URL (`side`, `g`, `c`, `m`) so it can be saved as a view and the path above
  goes back up. A workbook month says it has one amount per category and no statement lines.
  The year history (the former Overview) follows below, unchanged.
- **`GET /api/cashflow/flows?month&person`**: the month by type, group and category with the
  month before, and twelve months of totals. **`GET /api/cashflow/lines`**: the lines behind a
  side, group, category or merchant. Both count the same lines as `mart.v_category_month`
  (workbook months keep the workbook, a split counts through its parts, transfers left out) and
  follow the Both/Hernan/Lauren switch, so Cash flow and Home follow it too. Grouping is on
  plain columns, named in Python, because SQL Server can't match bound parameters in GROUP BY.
- **Home** (`/`): the latest month as widgets: Needs you (lines to review, missing statements,
  cash running short), the month in numbers (money in and out vs last month, kept, net worth,
  lowest cash ahead), where it went (each bar opens Cash flow at that group), coming up in the
  next 14 days (from the forecast), goals (purchases like the new house, money held for
  others) and the Inbox. **Customize** shows, hides and orders the widgets per person
  (`home` setting, ADR-026).

## Consequences

- No new tables or views: the flows are read with SQLAlchemy over `core.transaction`.
- The year history on Cash flow doesn't follow the person switch yet (it reads the mart views).
- The Sankey scrolls sideways on a phone; the waterfall table and the drill-down carry the same
  numbers in text.
