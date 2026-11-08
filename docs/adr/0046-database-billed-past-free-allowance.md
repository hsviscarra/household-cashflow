# ADR-046: Keep the database running past the free allowance

Status: accepted (0.61.3, Nov 2026); amends ADR-001 and ADR-028's cost guard

## Context

On 8 Nov 2026 Azure SQL's free offer (100,000 vCore-seconds a month) ran out and the database
paused until 1 December, taking the app down. At 0.5–2 vCores and a 60-minute auto-pause delay
the allowance is roughly 15–55 awake hours a month; nightly backups, deploys, bank sync and two
people's use spend that in days.

## Decision

Hernan chose to pay for usage instead of losing the app for weeks:

- `freeLimitExhaustionBehavior: BillOverUsage`: the free allowance is used first, then seconds
  awake are billed. Still serverless with a 60-minute auto-pause.
- At most 1 vCore (`GP_S_Gen5_1`), half the previous ceiling.
- The monthly budget is $10, emailing at 50% and 100% of actual cost and when the month is
  forecast to pass it. A budget alerts; it does not stop charges.

The live database was switched with `az sql db update` and the budget with `az rest`; these
Bicep values keep a redeploy from switching them back.
