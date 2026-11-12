# ADR-084: A salary counts in the month it pays for

Status: accepted (0.93.0, Nov 2026). Replaces the early-salary rule of ADR-070.

Hernan, Nov 12 2026: he is paid around the 20th and Lauren on the last day of the month, both for
the month that follows. Counting each line in the month of its date, November showed no income
until the 20th, and what arrived then was December's money: every month looked like spending
without earning, and "free cash" and "left over" (ADR-073) meant nothing. ADR-070 had gone the
other way for one case, moving Lauren's payroll paid on the 1st or 2nd to the month before.

## Decision

- A **salary** (money in, category under the income group "Salary") received on the **15th or
  later counts in the next month**; received before the 15th, in its own month (a payroll that
  slips to the 1st is still that month's). Everything else counts in the month of its date:
  spending, bills, transfers, other income.
- Only `core.transaction.cash_month` changes. The line keeps its date, so statements, balances,
  net worth and Transactions are untouched.
- `payday.settle` sets the month for every new or changed line, called from a `before_flush`
  listener in `app.models`, so a category given later (a rule, Claude, a person) moves the line
  at that moment, and taking the category away moves it back. The loaders no longer decide.
- Migration 0051 moves the salaries already loaded from banks, points each one's recurring link
  at the same item's entry in its new month (or clears it), logs every change in
  `audit.change_log`, and its downgrade restores them. The workbook's months are left alone.
- The forecast follows: a salary item with a usual day of 15 or later is laid on that day of the
  month before the one it is planned in (cash arrives then; the month's plan still shows it).
- With no month asked for, the cash flow opens on the latest month that has started, since the
  next month can already hold its salary.

## Consequences

- Every month from July 2026 shows the income that funded it; months seen before this change
  show different income than they did. Each month still has one salary from each person.
- A month's cash flow is no longer the change in bank balances within its calendar days: the
  salary that funds it arrived 10 to 40 days earlier. The balances themselves don't move.
- The cutoff is one number (`payday.NEXT_FROM_DAY = 15`). A salary paid in the first half of a
  month for the following month would need its own rule.
