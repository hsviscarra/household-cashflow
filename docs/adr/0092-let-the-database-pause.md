# ADR-092: Let the database pause

Status: accepted (0.102.1, Nov 2026); amends ADR-046.

On Nov 13 2026 the cost guard (ADR-076) stopped the app: the resource group had spent $20.45 in
thirteen days. Azure's breakdown: SQL Database vCore $17.38, Container Apps $3.56, the rest
cents. The database's free allowance ran out on Nov 8 (ADR-046), so in five days it billed
about $3.50 a day: it was awake many hours every day, far more than anyone used the app.

Azure SQL serverless pauses only when, for the whole auto-pause delay, there are **no sessions**
and no CPU use. The app kept a connection pool, and a pooled connection is an open session: for
as long as an app replica was up, the database could not start counting toward a pause, and
after the replica went away it stayed billed for the 60-minute delay.

## Decision

- **No connection pool on SQL Server** (`NullPool` in `db.make_engine`): each request opens its
  connection and closes it, so between requests the database has no session. SQLite (tests,
  local) keeps its pool. The cost is a login per request, tens of milliseconds.
- **Auto-pause delay 15 minutes**, the shortest Azure allows, instead of 60. The Bicep value
  changes; the live database is changed with
  `az sql db update --auto-pause-delay 15` (deploys don't apply Bicep).

## Consequences

- The database is billed for the minutes it works plus 15, not for as long as the app is up plus
  60. Every deploy still wakes it (migrations), as do the 6 am check-in, the bank sync and the
  nightly backup.
- Coming back after 15 quiet minutes means waiting for the resume (up to a minute) more often.
- Not found: why the app itself was up about half of every day (the Container Apps charge).
  With no pool that no longer keeps the database awake, but it is worth finding.
- Releases cost money: each of the twelve deploys of Nov 12 woke the database for over an hour.
  Small changes are grouped into fewer releases from now on.
