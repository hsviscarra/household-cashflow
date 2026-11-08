# ADR-048: The lines behind every number, fixed in place

Status: accepted (0.63.0, Nov 2026)

## Context

Hernan: "Salary in October says 12,684 but I think that is not correct... I would like to drill
down and check the details, who transferred to who, links to the source files... and be able to
reclassify there, search for other items if they are missing." The yearly by-category table on
Cash flow had no way into its numbers, and drill-downs elsewhere were read-only.

## Decision

- A shared **lines panel** opens over the page (a side sheet; Back or Escape returns to the same
  spot). It lists every line behind the number with date, description, account, person, who it
  was with, its type when not plain income or spending, whether it is a synced line waiting for
  its statement or a workbook amount, notes, and a link to the statement.
- Each line has a category picker; with "make it a rule" ticked a change also saves a rule for
  that merchant. Totals and To do refresh after each change.
- **Missing something?** searches every line from the month before to the month after, counted
  in the cash flow or not (transfers too), by description, merchant or notes. Found lines get a
  category picker, or **Move here** when the panel is for one category.
- Cash flow's yearly table: every amount opens the panel for that row and month (by group, or by
  category for savings and payments, with the row's type). Spending's drill-downs get **Fix or
  find lines**, which opens the same panel.
- API: `/api/cashflow/lines` gains a `type` filter and returns `category_id`,
  `statement_file_id`, `counterparty`, `merchant_key` and `cash_month`; new
  `GET /api/cashflow/search?q=&month=` (up to 100 lines).

## Consequences

- Any suspicious number can be explained and corrected without leaving the page. Since 0.63.2
  Home's Money in, Money out and Where it went bars open the panel too (KpiCard `onOpen`).
