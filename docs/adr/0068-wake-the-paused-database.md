# ADR-068: Wake the paused database instead of failing

Status: accepted (0.78.3, Nov 2026)

## Context

The Azure SQL free offer is serverless: after an idle hour it pauses, and the first login wakes
it, which can take up to a minute. The nightly books check ran Claude's `data_status` tool while
the database slept; the login timed out on both tries and the run reported nothing.

## Decision

Every engine (the app's and the read-only MCP login's) is made by `db.make_engine`, which for SQL
Server waits 60 seconds per login and, when the error means "not awake yet" (HYT00 login timeout,
08001, 40613, 40197, 40501), tries again after 10, 20 and 30 seconds. Any other error, such as a
wrong password, fails at once.

## Consequences

A call that wakes the database can take about a minute and a half instead of failing. Auto-pause
stays on, so the free offer still costs nothing while idle.
