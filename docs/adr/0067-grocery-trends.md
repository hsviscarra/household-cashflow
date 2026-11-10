# ADR-067: Grocery trends

Status: accepted (0.78.0, Nov 2026)

## Context

Groceries showed one month at a time and six plain columns. Hernan asked for a better chart, more
history, comparisons between months and the patterns in how the household shops.

## Decision

- `groceries.trends(db, month, months=12)` and `GET /api/spending/groceries/trends` return, for
  6, 12 or 24 months: each month's statements spending, invoiced amount, trips (supermarket
  invoices), average basket and amount by aisle; cells of month × aisle × type × brand so the
  page compares any two months by any of the three without another call; spending by day of the
  week; price movers (unit price the first and last month a product was bought in the period);
  products first bought this month; regulars (bought in 3 of the 6 months before) not bought.
- Groceries gets a **Trends** view next to Overview and Products: four tiles (average month,
  highest and lowest, trips and basket, usual shopping day), stacked columns by aisle with the
  statements' spending as a line and the numbers in a table, Compare two months (aisle, type or
  brand, biggest change first), this month against the usual, shopping days, prices up and down,
  new products and skipped regulars.
- A new `StackedColumns` chart in `components/charts.tsx`; the Overview's six-month chart uses it
  too. Seven aisles take the category palette; the rest share one color.
- All of it is computed from data already stored; no schema change.

## Consequences

The comparisons rest on invoices, so months whose invoices didn't reach the email look smaller;
the statements line shows the real spending beside them.
