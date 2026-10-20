# ADR-004: A month counts from the Excel history or from statements, never both

- Status: accepted
- Date: 2026-10-20

## Context

The Excel history is a cash view: a card bill counts as one "Capital One 4,000" line in the month
it was paid. Statements itemize purchases and treat card payments as transfers. A statement cycle
crosses months (Pichincha Jun 13 – Jul 12), so loading it puts itemized June purchases into a month
the workbook already covers with its own card-payment row. Counting both would overstate June.

## Decision

- The mart views (`v_monthly_cashflow`, `v_category_month`) count a month's statement lines only
  when that month has **no** Excel history rows. Months with history keep the workbook figures.
- Statement lines in those months are still loaded, kept and listed on the Transactions page, with
  a note that the month counts from the workbook.
- Migration 0008 recreates the views; the 0004 definitions are frozen in
  `api/migrations/views/0004/` so older migrations stay reproducible.

## Consequences

- The history months (Aug 2019 – Jun 2026) are unchanged by statement loads; July 2026 on comes
  from statements as they are approved.
- A month is "complete" only when every account's statement covering it is loaded; F12 (month
  status) shows that. If Hernan later wants statement detail to replace a history month, that is a
  per-month switch to add then.
