# ADR-104: The season of all spending scales everyday spending

Status: accepted (0.113.0, Nov 2026). Corrects ADR-101's first point. No schema change.

## Context

ADR-101 read one season from everything spent and added, to each month ahead, what that
calendar month usually spends over or under a usual month at the level of all spending. On the
household's data that gave everyday spending of 8,831.03 in December and 0.00 in February
against an average of 2,370.65, and moved the chance of cash going under zero from about 10% to
about 51%. All spending's December holds bills the forecast already plans as recurring items
(yearly payments, school, the cards), so the whole difference was counted twice in part, and a
month with no everyday spending isn't believable.

## Decision

A month ahead gets the everyday average times that calendar month's index: if the household's
December runs 40% over a usual month, everyday spending in December is 40% over its average,
and a light month is lighter by its share, never nothing. Hernan chose this over subtracting
the planned bills from the whole difference (more exact, more ways to be subtly wrong) and over
turning seasons off.

The likely range still takes the season out of total spending's surprises at the level of all
spending, as before: that part compares like with like.

## Consequences

- If December's extra really is thousands on the cards beyond the planned card payments, this
  understates it; the likely range is where that shows.
- Once a group has two years of its own detail, groups take over (ADR-096) and this isn't used.
