# ADR-018: Statements count from a chosen month; the workbook becomes a reference

- Status: accepted
- Date: 2026-10-28
- Amends: ADR-004

## Context

F19 (issue #21) is the bulk historical load: load past statements oldest first, approve them
month by month, until the history is complete and the Cash Flow workbook can retire.

ADR-004 made the workbook win every month it covers. The workbook runs through June 2026, so
statements for January–June 2026 would be stored and then ignored. Hernan wants statement detail
from at least January 2026 (or June 2026), and to keep the workbook as a reference.

## Decision

- **One setting, "statements from".** It lives in `core.app_setting`, migration 0019. It is the
  first month whose statements count.
  - The months the workbook counts are `mart.v_excel_month`: every workbook month before the
    setting, or all of them when it isn't set.
  - The five mart views (monthly cash flow in both views, categories by month, spending lines,
    interest and fees) use `v_excel_month` in both directions:
    - statements don't count in workbook months;
    - workbook rows don't count in statement months.

    So no month is ever counted twice.
  - `recurring.excel_months` follows the setting, so Data Status, the Recurring grid and the
    projections all treat statement months as statement months.
- **Changing the setting never deletes anything.**
  - Moving it changes which source the views count.
  - Recurring items matched to workbook rows in months that now count statements are matched
    again, to the statements.
  - Clearing the setting restores ADR-004.
- **The workbook as a reference.** `GET /api/sources` covers every month both sources have. For
  each month it lists income and spending from each source, plus spending per group with its
  gap, biggest first. A gap usually means a missing statement or a different category. Data
  Status shows it next to the setting.
- **The backlog** on the Import page, with no new endpoint:
  - "Read all" reads every unread statement, oldest first, one request at a time, so one request
    can't time out.
  - Statements waiting for approval are grouped by the month they end in. "Approve N" approves
    those that tie out, in order, so each opening balance can be checked against the previous
    closing balance.
  - Drops over 50 files are uploaded in chunks.
- **Earlier migrations read frozen view copies** (`views/0018`). Migrations 0010, 0011, 0013 and
  0014 used to read the current view files, which now depend on objects created in 0019.

## Consequences

- Moving "statements from" back to January 2026 empties January–June until their statements are
  loaded and approved. Data Status lists what's missing, and the check shows how far each month
  is from the workbook.
- The workbook stays loaded. It retires in practice when the check's gaps are explained and the
  setting covers every month that matters.
