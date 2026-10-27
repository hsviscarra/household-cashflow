# ADR-008: Recurring entries: templates, month entries and the month grid

- Status: accepted
- Date: 2026-10-27

## Context

The Cash Flow workbook is mostly a grid of rows that repeat every month (salaries, office rent,
the BIESS loan, condo fee, the card payments, the empleada…), with the actual amounts for past
months and a plan for the rest of the year. F11 (issue #13) replaces that grid: templates,
generate a month, copy forward and to a range, change from month X, matching to statement lines
and a month grid. Done when the 2026 workbook rows are reproduced in the grid.

## Decision

- **Three tables (migration 0012).**
  - `core.recurring_template`: name, category, type, start and optional last month, optional
    account, description pattern and tolerance (default 10%), and the workbook row it came from
    (block, group, label).
  - `core.recurring_amount`: the template's amount from a month on. "Change from month X" replaces
    the changes from X on with one row.
  - `core.recurring_entry`: one per template and month, with the expected amount, `is_override`
    when that month was set by hand (or copied), and `planned` or `skipped`.
  - `core.transaction.recurring_entry_id` links the lines that paid an entry. Several lines can
    pay one entry (two halves of a salary). "Matched" is derived from the links, never stored.
  Amounts are signed like transactions: income positive, everything else negative.
- **Month operations.** Generate creates the missing entries of the active templates. Copy
  writes a month's expected amounts (and skips) to every month of a range, at most 36, and leaves
  months with linked lines alone. A change from month X updates every later entry that isn't an
  override. Editing one cell makes it an override; "back to the template amount" undoes it.
- **Matching.**
  - It runs after an import is approved, after the workbook is reloaded, after generating or
    copying a month, and on demand.
  - In months covered by the Excel history (ADR-004), only workbook lines are linked, and a
    template made from a workbook row links that row's cell exactly.
  - Other months link statement and manual lines of the template's category within tolerance
    (at least 1.00), on its account (the line's or, for a matched transfer, the other side's,
    ADR-007) and containing its pattern when those are set. An uncategorized line qualifies
    through a pattern.
  - The closest single line wins. Otherwise lines that no other pending entry could take are
    linked together when their sum is within tolerance.
  - An entry with lines is never re-matched. Skipping or unlinking frees its lines, and a line
    can be linked by hand.
  - Every link and unlink is written to `audit.change_log`.
- **From the workbook.** "From the 2026 sheet" lists the sheet's income and expense rows. A row is
  ticked when it has values in three or more months or a planned value. Each chosen row becomes a
  template (amount = its latest value; the start month is its first value), and the year gets one
  entry per month with a value: past months link to the history lines, plan months are expected.
- **The plan.** The Overview's plan for a month comes from its planned entries when it has any,
  otherwise from the workbook's plan (`core.budget`).

## Consequences

- Run against the real workbook, the 2026 grid matches the sheet cell by cell for the 25 rows
  chosen by default (300 cells, no differences). Real statements link BIESS, Empleada IESS and
  the salary in their months.
- The four credit-card rows share the *Card Payment* category and their amounts vary a lot.
  They match statement lines only once each template has its account (or a wider tolerance).
- One-off rows in the sheet (Travel, a single insurance payment) stay out unless ticked; they are
  ordinary transactions.
