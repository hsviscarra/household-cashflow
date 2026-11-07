# ADR-041: Bills that don't come every month, as a monthly set-aside

Status: accepted (0.57.0, Nov 2026)

## Context

Phase 2 of the improvement plan. Insurance, matrícula, SOAT and other bills that come every few
months make January and September look like bad months. Bills already carry how often they repeat
(`every_months`, ADR-031), so the app can say how much to put aside each month without new data.

## Decision

- `GET /api/budget/{YYYY-MM}/yearly-bills`: every active expense template that repeats every 2
  to 12 months, with its amount when next due, the month it's next due, the share per month
  (amount ÷ months, rounded up to the cent), the months to go (this month through the due month)
  and what should be set aside by now (the share × the months since it was last due, this one
  included; the whole amount in its due month). Soonest first.
- The Budget page lists them under the groups with the total to put aside each month.
- No schema change: it reads the recurring templates and their amounts.

## Consequences

- The set-aside isn't a separate account; put it in savings or a goal (ADR-040) if you want it
  kept apart.
- One-off bills (`every_months` 0) and monthly ones aren't included.
