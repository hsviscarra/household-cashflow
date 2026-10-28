# Backups and restore

How the database is backed up, how to check it, and how to restore it (F17, ADR-016).

## What runs

| Job | When (Quito) | What it does |
| --- | --- | --- |
| `cashflow-backup` | Every night, 03:17 | Exports the Azure SQL database to a BACPAC in the private `backups` Blob container (`db/cashflow-YYYYMMDD-HHMMSS.bacpac`). Then it writes a manifest next to it, with the size, SHA-256, migration version, every table's row count and the transactions' total. |
| `cashflow-drill` | The 2nd of each month, 04:17 | Restores the latest backup into a throwaway SQL Server running inside the same job, then compares it with the manifest. The result goes to `drills/drill-*.json`. |

- **Retention:** a lifecycle rule deletes backups after 30 days. Drill results are kept a year.
- **Sign-in:** both jobs use the `cashflow-backup-id` managed identity, which is the SQL server's
  Microsoft Entra admin and may write only to the `backups` container. No passwords are stored.
- **Where to check:** Data Status → **Backups** shows the last backup and the last drill. It turns
  amber when the backup is more than 36 hours old, or the drill is more than 40 days old or
  failed.
- **Cost:** about $0. The export wakes the free-offer database for a minute or two each night, a
  few thousand of the 100,000 vCore-seconds a month. The jobs use the Container Apps free grant,
  and the backups are cents of Blob storage.

## Set up (once)

After the PR that adds F17 is merged and deployed (`deploy.yml` builds the backup image):

```bash
az login                         # as the subscription owner
./infra/azure/setup-backups.sh   # from the repo root
```

The script:
1. Creates the identity, the SQL Entra admin, the retention rule and both jobs.
2. Tells `deploy.yml` the job names (the `AZURE_BACKUP_JOBS` variable), so every deploy updates
   their image.
3. Runs one backup and one drill, and prints the results.

It doesn't touch the app, and it is safe to re-run.

## Run one now

```bash
az containerapp job start -g rg-cashflow -n cashflow-backup   # a backup
az containerapp job start -g rg-cashflow -n cashflow-drill    # a restore drill
az containerapp job execution list -g rg-cashflow -n cashflow-drill -o table
```

The logs of each run are in the portal: Container Apps job → Execution history → Console logs.

## Restore production

Restore when the database is lost or damaged, or to undo a bad data change older than
point-in-time restore (Azure keeps 7 days on the free offer; use that first for recent mistakes:
portal → SQL database → Restore).

1. **Pick the backup.** List them, newest last:

   ```bash
   ACCOUNT=$(az storage account list -g rg-cashflow --query "[0].name" -o tsv)
   az storage blob list --auth-mode login --account-name "$ACCOUNT" -c backups \
     --prefix db/ --query "[].name" -o tsv
   ```

   Your account needs **Storage Blob Data Reader** on the storage account (portal → Access
   control).
2. **Download it**, and its manifest, to compare after the restore:

   ```bash
   az storage blob download --auth-mode login --account-name "$ACCOUNT" -c backups \
     -n db/cashflow-YYYYMMDD-HHMMSS.bacpac -f restore.bacpac
   ```

3. **Import into a new free-offer database** (the free offer allows up to 10 per subscription,
   and a database created any other way is billed). In the portal: SQL server → **+ Create
   database** → name `cashflow-restored` → apply the free offer → **Auto-pause** when the limit is
   reached. Then:

   ```bash
   sqlpackage /Action:Import /SourceFile:restore.bacpac \
     /TargetConnectionString:"Server=<server>.database.windows.net;Database=cashflow-restored;Authentication=Active Directory Interactive;Encrypt=True"
   ```

   Signing in with Entra needs your account to be the server's Entra admin. Alternatively, use the
   SQL admin login and password from `bootstrap.sh`, with
   `User ID=cashflowadmin;Password=...` in place of the `Authentication` part.
4. **Check it** against the manifest: Data Status → the months, and the row counts in the
   manifest's `tables`.
5. **Point the app at it.** In the portal: Container App → Secrets → `database-url` → change
   `/cashflow?` to `/cashflow-restored?`, then restart the revision. Or rename the databases
   (old one to `cashflow-old`, restored one to `cashflow`) so nothing else changes.
6. Once you're satisfied, delete the old database.

## Restore locally

To look at a backup on your computer, import it into the Docker SQL Server:

```bash
docker compose up -d sqlserver
sqlpackage /Action:Import /SourceFile:restore.bacpac \
  /TargetConnectionString:"Server=localhost,1433;Database=cashflow_restore;User ID=sa;Password=<MSSQL_SA_PASSWORD>;TrustServerCertificate=True"
```

You can also run the drill against it with the backup image:

```bash
docker run --rm --network host -v "$PWD/backups:/backups" -e BACKUP_DIR=/backups \
  -e DRILL_SERVER=localhost,1433 -e DRILL_DATABASE=cashflow_restore -e DRILL_USER=sa \
  -e DRILL_PASSWORD=... -e DRILL_TRUST_CERT=1 ghcr.io/hsviscarra/household-cashflow-ops drill
```

Keep restored copies off shared or synced folders. They hold the household's whole history.
