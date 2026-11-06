# ADR-033: Forecast and the month in ten answers

Status: accepted (0.49.0, Nov 2026)

## Context

The redesign's ninth and last PR (ADR-025). The projection gave one total cash line for three
months: it couldn't say which account would run dry, it counted money held for other people as
ours, and it had no way to try a change. The monthly report was 3 to 5 findings that needed a
button press, not the questions we actually ask at month end.

## Decision

- **Forecast options** on `GET /api/projections`: `horizon` 1, 3 or 12 months; `average_over`
  3, 6 or 12 months of everyday spending; `floor` (warn under this balance, default 0);
  `include_held` (default no). Other values are a 422. The choices are saved per person
  (settings key `forecast`, ADR-026).
- **Per account**: recurring items, loans and purchase installments carry their account (a
  purchase takes the account of the last line in its category). Each bank account gets its own
  daily run from its latest balance with only its own items, its lowest day, the first day it's
  under the floor and how much to move in (`floor − lowest`). Everyday spending and items
  without an account stay in the total only. Recurring items use their day when set (ADR-031).
- **Money held for others**: personal-loan items linked to a person (ADR-030) are taken off
  the starting cash unless `include_held`, so the forecast is our money only.
- **What if**: `POST /api/projections/scenario` takes the options and up to 20 changes (name,
  signed amount, every month on a day or once on a date, optional account) and returns the
  projection plus `base` (lowest, first short day, end cash without the changes). The page
  offers three: move money between accounts each month (two changes), something each month,
  and a one-off. Changes are not saved.
- **The page** ("Will cash cover what's coming?"): horizon switch, a heads-up for each account
  under the floor, How it's calculated (starting balances, bills, average months, held money,
  floor, each one editable in place), What if, then the day-by-day chart with the total and
  each account as lines and the floor dashed, the month table and the alerts.
- **Ten answers**: `GET /api/reports/{month}/answers` answers, live and without Claude: did we
  spend more than usual, what was unusual, did every bill get paid, are we on track for the
  purchase, will cash be short next month, where could we save, what did cards and banks cost,
  how much is someone else's money, did net worth go up, can I trust these numbers. Each has a
  short answer, one sentence, a tone and a link to the page with the detail. The report page
  shows them above the findings, which stay.

## Consequences

- Account runs ignore transfers between our accounts unless entered as a what-if, so an account
  topped up by hand every month looks short; the heads-up says how much to move.
- "Will cash be short" only looks ahead from today; for older months it answers "—".
- The answers are computed on each visit (a dozen queries); fine for one household.
