# ADR-099: Explore: build your own view of spending

Status: accepted (0.109.0, Nov 2026). Plan item B4. No schema change.

## Decision

- **A view** is a measure (amount spent, number of lines, average line), what goes in the rows
  and in the columns (group, category, merchant, who, account, country, fixed or variable,
  month, year), a period (last 3 to 24 months, this year, last year) and a filter (who, one
  group). `/explore`, a tab of Spending.
- **One grouped query.** `GET /api/explore` groups `mart.v_spending_line` (the lines every
  spending page reads) by the two dimensions and returns the table with its totals.
  `services/explore.py`: `records` asks the database, `pivot` is pure. Sums and counts travel
  together to the end, so an average is right in every cell and total. Month and year share a
  column in the database: grouped once, read as both.
- **Something to read, not an export.** At most 50 rows (the smallest add up into "Everything
  else") and 24 columns; time is read in order and never folded, and with too many months the
  latest are kept. At most 60 months.
- **Table or chart, and CSV.** The chart stacks the seven biggest rows over the columns (or
  draws one column per row without columns); the table always has everything.
- **Saved and pinned.** A view is kept by name in the person's settings (`explore:views`, at
  most 20); a pinned one shows on Home in "Your views" with its first six rows and its total.
  The Home card isn't drawn when nothing is pinned.

## Not in this release

- Money in, savings and transfers as measures: they aren't spending lines, and each has its own
  rules for what counts (ADR-073). Explore is over spending until one of them is asked for.
- A custom date range and more filters (account, country, category): the endpoint takes them
  already; the page offers the ones used most.
- TanStack Table: the tables here are small and read-only; nothing in them needs it (YAGNI).
