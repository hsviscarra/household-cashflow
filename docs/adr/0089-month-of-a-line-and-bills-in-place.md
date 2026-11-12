# ADR-089: The month of a line, and bills fixed where they are listed

Status: accepted (0.98.0, Nov 2026). Hernan approved the column on Nov 12 2026.

Three things from Hernan using the app on Nov 12:

- Home's "Money in" for November held a transfer of Oct 23 that is a yearly bonus for October.
  ADR-084 counts a salary received on the 15th or later in the next month; a bonus in the same
  category is not next month's pay, and there was no way to say so.
- Bills listed items as late whose day was wrong, and items that no longer apply, with nothing
  on that screen to change them (only the year grid).
- To do was ordered by count and date, not by what matters most.

## Decision

- `core.transaction.month_override` (DATE, nullable; migration 0053, downgrade drops it). When
  set it wins in `payday.settle` over the rule that works `cash_month` out. `payday.move` sets
  or clears it: only the month of the line's date or the one before or after, logged in
  `audit.change_log` (column `month_override`). `PATCH /api/transactions/{id}` takes
  `counts_in` (null hands the line back to the rule). A bill the line paid is unlinked and the
  new month is matched again.
- The lines panel (the lines behind any number, ADR-048) has "Counts in" on each line, so the
  fix is made where the wrong number is seen: Home → Money in → the line → October.
- Bills: each row has Change, with its day, "Skip this month" (or expect it again) and "Doesn't
  apply any more". The last calls `recurring.stop`: the item ends the month before (or is turned
  off when it never ran) and its planned, unpaid entries from that month are removed; what was
  paid stays. `POST /api/recurring/templates/{id}/stop`. The bill list carries the month's
  `entry_id`.
- To do's Needs a category, Who or what is it and Transfers are ordered by the money at stake.

## Consequences

- An override stays until cleared; a later category change no longer moves that line.
- The rule itself is unchanged: other bonuses in the Salary category paid after the 15th need
  the same one-time fix, or their own category outside Salary.
