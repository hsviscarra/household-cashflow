# ADR-101: The plan's leftovers: a season from all spending, Explain, chart tools, table filters

Status: accepted (0.111.0, Nov 2026). Finishes plan items B2, B3, C2 and D1. No schema change.

## Decision

- **One season of all spending** (C2). When no everyday group has two years of its own
  (ADR-096: the workbook kept everyday spending inside card payments), the forecast reads one
  season from everything spent in whole calendar years (`measures.spent_by_month`, 8 years
  back): the median, over those years, of each calendar month against the year's average. A
  month ahead gets the everyday average plus what that month usually spends over or under a
  usual month at today's level (the last twelve months), never under zero. In the workbook's
  years a card's purchases count in the month the card was paid, so the season is already in
  cash timing. The same season is taken out of the range's surprises. Once a group has its own
  two years, groups take over. The page says which is in use; "Follow the seasons" turns it off.
- **Explain** (D1). `ChartTools` puts "Explain" beside a chart; it writes a question about that
  chart (its period and what it shows) into Ask Claude and opens the panel. It does not send:
  a question costs, so the person sends it. On Spending, Forecast, Net worth, Years ahead,
  Saving, Groceries and Home's cash flow.
- **Chart tools** (B3). The same component gives a chart its period and "Download CSV". Home's
  cash flow takes 6, 12 or 24 months; Net worth's trend 12, 24 or 36 (`GET /api/networth?months`,
  capped at 36 because each month is valued on its own). Each choice is remembered per person.
  CSV writing is one module (`csv.ts`).
- **A filter bar on the shared table** (B2). `DataTable filter` builds it from the columns: one
  value of any column that can be grouped, an amount range on the first totalled column, and a
  date range when a column has a `date`. On Deductions, By category, Groceries' products and
  Purchases' invoices; Transactions keeps its own filters, which live in the address and saved
  views. Not remembered: a filter answers the question of the moment.

## Not done, on purpose

- "Group by" and "compare with" on Home, Net worth and Groceries' charts: those charts are one
  measure over time; splitting them is what Explore is for.
