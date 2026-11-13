# ADR-094: A chart with controls, and Groceries' products on the shared table

Status: accepted (0.104.0, Nov 2026). Plan items B3 (first chart) and B1 (last list). Shipped as
one release: each deploy wakes the database and costs money (ADR-092).

## Decision

- **Spending over time has controls.** Period (3, 6, 12 or 24 months, or this year), Split by
  (nothing, group, category, who, account or country) and Show (amounts, share of each month, or
  the numbers as a table). The choice is the person's and is remembered (setting
  `chart:spending`). Download CSV gives the same numbers as a file.
- **The server groups.** `GET /api/spending/series?month&months&by&person` reads
  `mart.v_spending_line` once, grouped by month and the chosen dimension, so a 24-month chart is
  one query and not 24. At most `MAX_SERIES` (7) series are drawn; the smallest are added
  together as "Everything else", so the series of a month always add up to that month's
  spending (tested against the trend). The window is capped at `MAX_SERIES_MONTHS` (36).
- **One component.** `SpendingChart` owns the controls, the stacked columns, the legend and the
  table; the page gives it the month and the person. Clicking a column still opens that month.
- **Groceries → Products on `DataTable`** (ADR-091): columns (aisle, type, brand, store, bought,
  times, unit price), order, sort, grouping with subtotals and a total of what was spent. The
  label editor opens under the row instead of replacing it.

## Not in this release

- The same controls on Home, Net worth and Groceries' charts, and "compare with" (another
  period or last year, side by side): each needs its own series endpoint; this one proves the
  shape first.
- Purchases stays a list of cards: it is a redesign, not a move to the table.
