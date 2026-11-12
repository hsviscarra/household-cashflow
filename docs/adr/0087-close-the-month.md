# ADR-087: Close the month

Status: accepted (0.96.0, Nov 2026). Plan item A8.

The month-end work was spread over Data health, To do, the Inbox's "decided on its own" list, the
report and Purchases. Hernan wanted one screen with only the exceptions, prepared by the app.

## Decision

- `services/month_close.py` gathers, for one month, what other services already know: what keeps
  it from being complete (`status.month_status`), groups well above their three-month average
  (`projections.alerts`), the rules the app saved by itself while the month's lines arrived
  (`inbox.recent_auto`), how many invoices the month has, and whether its report exists. It
  computes nothing new.
- A month is **ready to close from the 3rd** of the next month (`CLOSE_DAY`). From that day the
  daily check-in writes the month's report if it has none (Claude when it is on, rules
  otherwise) and the watchdog emails once: "October is ready to close" (kind `close`, which can
  be turned off like the others).
- **Closing records who and when** in `core.app_setting` (`month-closed:YYYY-MM`) and writes the
  report if missing. It locks nothing: lines can still be edited, and Reopen removes the mark. A
  month with things missing can be closed; the screen has shown them.
- The screen (`/close`, a tab of Monthly report) lists Missing, Unusual and Decided by the app,
  each with its action (the page that settles it, the month's lines by category, Undo), and a
  reminder to download the month's list of received documents from SRI en línea and upload it on
  Purchases, since some invoices never reach email.
- No schema change.

## Consequences

- Closing is a record, not a lock. If a locked month is wanted later, it needs its own decision
  (what happens to a late statement).
- "Unusual" is by group, not by line: single unusual charges are still emailed the week they
  happen (ADR-082).
