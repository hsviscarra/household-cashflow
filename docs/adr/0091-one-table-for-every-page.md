# ADR-091: One table for every page, starting with Deductions

Status: accepted (0.100.0, Nov 2026). Plan item B1; Hernan chose Deductions first (Nov 12 2026).

Only Transactions let a person choose columns. Every other list was fixed, and several weren't
tables at all: Deductions listed invoices as rows of text with controls, which can't be sorted,
grouped or added up.

## Decision

- `components/DataTable.tsx`: a page describes its columns (`cell`, and optionally `sort`,
  `total`, `group`, `align`, `fixed`); the component draws the table and gives the person:
  columns to show or hide and move left or right, a click on a header to sort, "Group by" with a
  subtotal row per group, and a totals row.
- The layout (columns in order, sort, group) is saved per person and table with the other
  preferences (`prefs.useTableLayout`, key `table:<name>`, the key `useColumns` already used),
  so it follows them between devices.
- **No table library.** The plan named TanStack Table; sorting, grouping and a column list for
  tables of a few hundred rows came to about 200 lines with no new dependency, so it wasn't
  added (YAGNI). If a page needs virtual scrolling or pivoting, that decision is reopened.
- **Deductions' invoices** are the first page on it: Supplier (always shown), Date, Before VAT,
  Whose, Category, For the SRI by default; Invoice number, Paid and Paid with can be added.
  Group by supplier, month, whose, category or SRI group. "All from this supplier" became one
  switch above the table instead of a checkbox on every row.
- Pages move to it one at a time, each as its own release: By category, Bills' year grid,
  Groceries, then Transactions (whose own picker is replaced), and Purchases last, since it needs
  a redesign first.

## Consequences

- A wide table scrolls sideways on a phone; the list it replaced wrapped. The phone version
  (plan item D3) is where that gets its own layout.
- Transactions keeps its own column picker until it moves; both store under the same key shape.

## 0.101.0: By category and Groceries

- **Transactions → By category**: a category's lines are on the shared table. Who, Counts in and
  Note can be added; group by month, account, who, merchant or the month it counts in; the total
  is a row. A column can carry its own header (`Column.header`) for the "tick every line" box.
- **Groceries → Top products**: sort by price change or quantity, group by type of product.
- **Not moved: Bills' year grid.** It is a month-by-month matrix that is edited in place; its
  columns are the months, so choosing and sorting columns doesn't apply. It stays as it is.
