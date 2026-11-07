# ADR-038: The weekly digest

Status: accepted (0.54.0, Nov 2026)

## Context

Phase 1 of the improvement plan: the app should come to Hernan and Lauren instead of waiting to
be opened. It has no mail service, and adding one (SendGrid, Azure Communication Services) means
another account, secret and cost. The Gmail script (ADR-020) already runs every morning in
Hernan's Gmail with the inbox token.

## Decision

- `GET /api/inbox` (the inbox token; Easy Auth already lets `/api/inbox` through) returns the
  digest: a subject, a one-line summary, sections of action items with links into the app, and the
  same as plain text and simple HTML in the Clear colors.
- Sections, each only when it has something:
  1. **Needs a category**: lines in the Inbox and how many merchants.
  2. **Bills this week**: late this month, or due in the next 7 days, with the account.
  3. **Cash running short**: an account under the floor in the next 30 days and how much to move
     (ADR-033), or total cash under zero.
  4. **Unusual charges**: the last 7 days' charges of $50 or more and at least 3 times the
     merchant's median over the 6 months before (two earlier charges needed).
  5. **Statements to bring in**: last month's still missing (this month's aren't due yet).
  6. **Gastos personales**: invoices without a person or a category this year (ADR-036).
- The summary compares money out this month so far with the same days of last month.
- The Gmail script's daily run sends it on Mondays with `MailApp` to `DIGEST_TO` (default: the
  script's own account); `testDigest()` sends it on demand. Three tries 20 seconds apart wake a
  sleeping app.

## Consequences

- One paste of the updated script into the Apps Script editor and one run of `testDigest()` to
  allow sending email; no Azure change.
- Push notifications to phones wait for the installable app (phase 4); the email is the channel.
