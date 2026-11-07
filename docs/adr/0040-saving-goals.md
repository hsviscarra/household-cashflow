# ADR-040: Saving goals

Status: accepted (0.56.0, Nov 2026)

## Context

Phase 2 of the improvement plan. The only goal the app followed was the new house, as a purchase
in progress on Net worth (ADR-032). An emergency fund, school, a trip or a car had no place, and
nothing said whether the money put aside each month was enough.

## Decision

- **`core.goal`** (migration 0033): name, target amount, optional date, where the money is
  (`item_key`: a bank account `account-<id>` or a balance-sheet asset `holding-<id>`), an amount
  saved typed by hand when it isn't in one place, a planned monthly amount, active/paused, notes.
- **Saved so far** = the linked item's latest value (a purchase in progress counts what's paid),
  else the typed amount.
- **Pace**: months left counts this month through the target's month. Needed per month =
  what's left ÷ months left, rounded up to the cent. Projected = saved + planned × months left.
  Status: *reached*; *open* (no date); *late* (date passed, not reached); *on pace* (projected
  reaches the target); else *behind*, with the monthly amount that would get there.
- API: `GET /api/goals` (goals and the places a goal can link to), `POST`, `PATCH` (only the fields
  sent; null clears), `DELETE /api/goals/{id}`. Page: Goals, under Plan.
- **Home**: the Goals widget lists active goals with their pace line; a purchase that a goal
  follows shows once, as the goal.

## Consequences

- A goal doesn't move money or add to the forecast yet; the forecast's what-ifs (ADR-033) can
  model the monthly transfer.
- Two goals linked to the same account each count its whole balance; split the money into
  separate accounts or type the amounts by hand.
