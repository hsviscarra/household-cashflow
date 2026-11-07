# ADR-043: Recurring bills found in the statements

Status: accepted (0.59.0, Nov 2026)

## Context

Phase 3 of the improvement plan. Recurring items (ADR-031) were all typed by hand or picked from
the Cash Flow sheet, so a new phone plan, insurance or streaming service stayed out of the Bills
page until someone noticed it. The subscription finder (ADR-011) already spots charges that repeat
at a steady interval with a similar amount.

## Decision

- `GET /api/recurring/found`: the subscription finder's active monthly, quarterly and yearly
  charges that have a category, none of whose lines is linked to a recurring entry, and whose
  latest line no active recurring item would match (same category, same account when the item has
  one, and its pattern in the description). For each: the merchant, how often (1, 3 or 12 months),
  the typical amount, the most used category and account, the person when all lines share one, a
  match pattern (the whole words every description starts with, at least 3 characters), the usual
  day (median), how many charges, the last date, the next expected date and up to 3 examples.
  Most expensive per month first.
- The Recurring page (and the Bills page that embeds it) shows them as "Found in your statements"
  with Add and Not now. Add creates an ordinary expense recurring item from the values above,
  starting in the month of the last charge. Not now is kept per user in the setting
  `bills_found_dismissed` (last 200 merchants).
- Uncategorized repeating charges are left out: a recurring item needs a category, and the Review
  list is where those get one.
- No schema change.

## Consequences

- New bills reach the Bills page, the money calendar and the forecast with one click instead of
  being found by hand.
- Charges that repeat but aren't bills (a weekly coffee) only show if they are monthly, quarterly
  or yearly; Not now hides the rest for good.
