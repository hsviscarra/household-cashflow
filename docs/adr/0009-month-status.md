# ADR-009: Month status: complete, or what is missing

- Status: accepted
- Date: 2026-10-27

## Context

F12 (issue #14) adds the Data Status page: the load log, coverage per source, pending items
and continuity gaps. It is done when each month shows complete or what is missing. Statements
don't follow calendar months: card statements run mid-month to mid-month (for example the
4th to the 3rd), and the tie-out's continuity check leaves non-adjacent
statements to this page (stage.py).

## Decision

- **Which months.** Months the Excel history covers are complete by definition (ADR-004) and
  shown as one line: "Through June 2026: complete, from the Cash Flow sheet". Every month from
  the one after it up to the current month is checked. With no workbook, checking starts at the
  first statement's month.
- **A month is complete when none of these is open:**
  - *Statements:* every active account has approved statements covering every day of the month.
    Coverage is the union of the statements' periods, counted by day, so a card month needs two
    statements. The current month is checked up to today. The item names the uncovered days
    ("Capital One Venture: no statement for Oct 4–27", an example), or the whole month when no statement
    touches it.
  - *Imports:* a statement whose period overlaps the month waits for approval or doesn't tie out.
  - *Lines without a category* (F9) and *transfers without their other side* (F10).
  - *Recurring items* expected in the month that no line paid and that weren't skipped (F11).
  - *Balance breaks:* consecutive statements of an account (at most 7 days apart) whose opening
    balance differs from the previous closing balance. This can only happen when statements
    were approved out of order, because the tie-out refuses it otherwise. It shows in the month
    the later statement starts.
- **Each item links to its fix:** Import, the batch, Review for the month, or the Recurring
  grid.
- **Inactive accounts aren't expected.** An account the household doesn't track is switched off
  in Settings → Accounts.
- **Computed in Python** (`services/status.py`, `GET /api/status`), not a mart view. Coverage
  needs interval unions over statement periods and reuses the F9–F11 services, and the result
  is a small per-month list. No schema change.
- **The page also shows** a coverage table (accounts × months: full, part with days, none) and
  the last 30 rows of `audit.load_log`.

## Consequences

- On the real data the page says exactly which statements to upload to close July–October
  2026, plus the open categories, transfers and recurring items.
- A month can only become complete once the following card statement is in, which is correct.
- Months are recomputed on every request; if this gets slow it can move to a materialized table.
