# ADR-078: The arrival watchdog

Status: accepted (0.87.0, Nov 2026)

Improvement plan, item A5. On Nov 11 2026 the Diners statement that closed Nov 3 had not arrived
and nothing said why: the Gmail script (ADR-020) may have stopped, and the app can't tell a quiet
inbox from a dead script. Hernan chose alerts by email only.

- **Heartbeat.** The script calls `GET /api/inbox?alerts=true` (the inbox token) at the end of every
  run, even when the import failed. The app keeps the time in `core.app_setting`
  (`gmail-script:last-seen`). Two days without a call and the script is `silent`: Data Status
  shows a red note with what to do, Home's "sources need you" pill counts it, and Claude's
  `data_status` tool returns `gmail_script`, so the daily scheduled check reports it. Before the
  first call the state is `never`, with a note to paste the new `Code.gs`.
- **Alerts by email.** The same call answers with what is worth an email now: each statement
  that is `late` (ADR-072). The script sends one email from Hernan's Gmail (to `ALERTS_TO`, else
  `DIGEST_TO`, else the account), as it does the weekly digest (ADR-038): no mail service, no new
  secret. Each alert is sent once, remembered as `alert-sent:<key>` for 120 days; the next
  statement of the same account is a new alert.

Consequences: the script's own silence can't be emailed by the script. It is seen in the app and
by Claude's daily check, which runs outside Gmail. Hernan pastes the new `Code.gs` once. More
kinds of alert (an unusual charge, a bill due, a budget at 80%) join `watchdog.alerts` later
(plan item D4).
