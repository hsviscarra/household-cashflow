# ADR-093: Ticked rows with totals, find in a table, and one search box

Status: accepted (0.103.0, Nov 2026). Plan items B2 (in part) and D2. Shipped as one release:
each deploy wakes the database and costs money (ADR-092).

## Decision

- **Tick rows, see what they add up to.** `DataTable` takes `select`: it adds the tick column
  (and "tick every row shown"), shows a bar with the count and the sums of the ticked rows, and
  the page's actions for them. Transactions shows money out, in and net (transfers and split
  parents left out) and "Categorize as" for all ticked lines; By category uses the same ticks for
  its existing "Move ticked to".
- **Find in this table.** `DataTable` takes `search` (the words a row is found by) and filters as
  one types: every word must appear, in any order. On Deductions, By category and Groceries' top
  products. Transactions keeps its own filters, which also live in the address and saved views.
- **One search box.** Ctrl+K or ⌘K anywhere (and a Search button in the sidebar): pages and
  actions by their words, and whatever was typed as a search of the last 12 months of lines, or
  as an amount when it is a number. It only navigates; it asks the server nothing by itself.

## Not in this release

- Saved views beyond Transactions, and a date or amount range filter on every table: the layout
  of each table is already remembered per person; a filter bar per page is its own piece.
- Bulk "assign a person" and "mark as transfer": the API changes one line at a time, and those
  two have side effects (transfer pairing) that deserve their own endpoint and tests.
