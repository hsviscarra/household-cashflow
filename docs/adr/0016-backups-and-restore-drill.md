# ADR-016: Nightly BACPAC export and a monthly restore drill, inside Azure

- Status: accepted
- Date: 2026-10-28

## Context

F17 (issue #19) adds a nightly BACPAC export with 30-day retention and a documented restore
drill. It is done when a restore to a scratch database succeeds. The Azure SQL free offer has 7
days of point-in-time restore but no long-term retention. A BACPAC is also portable: it restores
on any SQL Server, including the Docker one.

## Decision

- **Inside Azure, with no stored passwords** (Hernan's choice, over a GitHub Actions workflow
  where the database copy would pass through a GitHub runner). Two Container Apps Jobs share a
  user-assigned identity (`infra/azure/backups.bicep`):
  - the identity is the SQL server's Microsoft Entra admin, so the export signs in with it;
  - it has Storage Blob Data Contributor on the `backups` container only.
- **Its own template and setup script.** `setup-backups.sh` adds these next to `main.bicep`'s
  resources. Re-running `bootstrap.sh` would reset the app's image and sign-in secret, so it is
  not used here. `deploy.yml` builds the backup image (`infra/ops/Dockerfile`: the app image
  plus sqlpackage) on every merge and updates the jobs, so they always run the deployed code.
- **The export writes a manifest after the file**, so a manifest means a complete backup. The
  manifest holds the size, SHA-256, migration version, every table's row count and the
  transactions' total.
- **The drill restores into a SQL Server that runs beside it in the same job:**
  - the server is Developer edition, used only for this check, and disappears with the job;
  - the runner checks the file's SHA-256, imports it, and compares the migration, every table's
    count and the total;
  - it records the result, pass or fail, then shuts the server down so the job can finish.

  This avoids a scratch Azure database, which can't be recreated on the free offer from code
  without risking a billed database. The drill also refuses to replace a database whose name
  doesn't end in "restore".
- **Retention by Blob lifecycle rules:** backups after 30 days, drill results after a year.
- **CI proves it on every PR,** against CI's SQL Server, in two ways:
  - the integration tests export and restore with sqlpackage into a scratch database;
  - the Docker job builds the backup image and runs a real export and drill with it.
- **Visible in the app.** Data Status shows the last backup and drill and turns amber when the
  backup is more than 36 hours old, or the drill is more than 40 days old or failed. No Azure
  Monitor alert: it would cost more than the $1 budget allows for.

## Consequences

- The backup schedule needs the one-time `setup-backups.sh`, run by the subscription owner,
  because it assigns a role and sets the Entra admin.
- Restoring production means importing into a new free-offer database and pointing the app at
  it (docs/runbooks/backups.md). Point-in-time restore stays the first choice for mistakes in
  the last 7 days.
- Each export wakes the free-offer database for a minute or two, a small share of the monthly
  allowance.
