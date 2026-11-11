# ADR-076: A $20 cost guard with a kill switch

Status: accepted (0.85.0, Nov 2026)

Since ADR-046 the database bills past its free allowance, and the only guard was a $10 budget that
emailed. Hernan wants a hard ceiling: "add more alerts on 20 USD, I don't want to go over that".
Azure budgets never stop anything by themselves, so the guard has two parts.

**Alerts (option 1).** `cost-guard.bicep` replaces the resource group's budget (same name, moved out
of `main.bicep`) with a $20 one that emails at 25, 50, 80 and 100 percent of actual spend and when
the month is forecast to pass $20. `cost-guard-sub.bicep` adds a $20 budget on the whole
subscription, in case something outside `rg-cashflow` costs money, and Azure's free cost anomaly
alert, which emails when a day's spend jumps against the usual pattern.

**Kill switch (option 2).** At 100 percent actual, the budget calls an action group that runs a
Logic App (`cashflow-kill-switch`) with its own managed identity, Contributor on the Container App
and the database only. It stops the Container App (no copies, no compute) and switches the database
to pause, instead of bill, once its free allowance is used. Nothing is deleted: data, backups and
settings stay. `setup-cost-guard.sh --restart` undoes both.

Consequences:
- The cap is soft by about a day: Azure's cost data lags 8 to 24 hours, so the kill switch fires
  after the spend crosses $20, and a few cents more can land.
- While stopped the app and the MCP endpoint are down; the nightly backup job still runs.
- The deploy identity can't assign roles or touch the subscription, so Hernan runs
  `setup-cost-guard.sh` once as owner (bootstrap.sh runs it for a fresh setup), and again yearly
  to renew the anomaly alert, whose schedule ends after a year.
- The Logic App's own runs cost fractions of a cent, inside the free grant.
