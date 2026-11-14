# ADR-107: Park Azure and run locally during development

Status: accepted (0.116.0, Nov 2026). No schema change.

## Context

The database bills for its hours awake past the free allowance (ADR-046), about $0.50 an hour at
one vCore; in November it cost $17 in five days before ADR-092 let it pause. While the app is being
built, every deploy wakes it and the scheduled jobs wake it daily. Hernan wants costs down for the
development phase without losing the Azure setup, because the app is meant to run there.

## Decision

A script, `infra/local/park.sh`, moves the household between Azure and the Mac:

- **down** copies Azure's database to SQL Server in Docker on the Mac and the statement PDFs to the
  local folder, then parks Azure: the app stopped, the backup jobs yearly, the database set to
  pause rather than bill, and deploys skipped (`deploy.yml` checks the repository variable
  `AZURE_PARKED`). Nothing in Azure is deleted. A paused serverless database bills storage only,
  which the free offer covers, so a parked setup costs about $0.
- **up** saves the parked Azure database to a file, recreates it empty with the free offer, copies
  the Mac's database and new PDFs up, restores the schedules, unsets the variable, starts the app and
  deploys `main`.
- The data moves with the backup tool's new `copy` command: export a BACPAC with its manifest,
  import into an empty database, and compare row counts, migration and the transactions' total.
  It only writes into an empty database, and on Azure only into one that already exists, since a
  database sqlpackage creates there isn't on the free offer. CI runs it against SQL Server.
- The Mac reaches Azure SQL through a firewall rule for its own address, removed when the script
  ends; passwords reach the containers by name, never on a command line.
- **Recreate rather than rename on the way up**: the Azure CLI documents the free offer as one
  database per subscription, so a second free database to swap in may be refused. The saved file,
  Azure's 7-day restore of deleted databases and the nightly backups cover the replaced database.

## Consequences

- While parked the app runs only on the Mac: nothing from a phone, scheduled Claude tasks only
  while the Mac is awake, emailed statements wait in Gmail.
- Only one copy is in use at a time; the parked cloud app is off, so that holds unless it's
  restarted by hand.
- The Azure and GitHub steps can't run in CI (they need Hernan's sign-in); they were exercised
  against stand-in `az`, `gh` and `docker` commands, and `DRY_RUN=1` prints them before a real run.
