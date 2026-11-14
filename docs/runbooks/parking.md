# Parking Azure: run the app on your Mac, and come back

While the app is still being built, the Azure database bills for every hour it's awake past its
free allowance, and every deploy wakes it. Parking moves the data to your Mac and leaves Azure set
up but asleep, at about $0 a month. Coming back moves the data up again. ADR-107 has the why.

## Before the first time

- Docker Desktop running, and in this repo a `.env` with `MSSQL_SA_PASSWORD` (`cp .env.example .env`).
- Signed in: `az login` (the subscription's owner) and `gh auth login`.
- The SQL admin password from `bootstrap.sh`, from your password manager. The script asks for it
  and never prints or saves it.
- On `main`, up to date: `git checkout main && git pull`.

To see what a run would change in Azure and GitHub without changing it, put `DRY_RUN=1` in front.
A dry run still does the copy (it only reads Azure), so it replaces the local database and opens
the temporary firewall rule for this Mac, which it removes when it ends.

## Park: `./infra/local/park.sh down`

About 15 minutes the first time (it builds the backup image).

1. Copies the Azure database into SQL Server on your Mac and checks it: every table's row count,
   the migration version and the transactions' total must match the backup it makes on the way.
   If they don't, it stops and Azure stays as it was.
2. Copies the statement PDFs from Blob storage into the app's local folder. The first time it
   offers to give your account the *Storage Blob Data Contributor* role it needs for that.
3. Parks Azure: stops the app, moves the backup jobs to once a year, tries to set the database to
   pause at its free allowance (Azure refuses in a month whose allowance is used up; harmless, since
   a paused database bills nothing), and sets the repository variable `AZURE_PARKED=true`, so
   merges to `main` no longer deploy. Nothing in Azure is deleted.
4. Starts the app at http://localhost:8000.

Then:
- **Claude's connection**: in Claude's config (docs/runbooks/claude-mcp.md) change the app's
  `/mcp` address to `http://localhost:8000/mcp` with the `MCP_TOKEN` from `.env`. The daily
  statement check and the IBKR save then work while the Mac is awake and Docker is running.
  Leave `READER_PASSWORD` empty in `.env` while parked: the read-only login from Azure doesn't
  carry over to SQL Server.
- **Emailed statements** can't reach your Mac; they wait in Gmail. Upload any you need on Import.
- After a restart of the Mac: `docker compose up -d`.

Use only the local app while parked. The cloud app is off, so that is the default.

## Come back: `./infra/local/park.sh up`

About 20 to 30 minutes, mostly the import.

1. Stops the local app, so nothing changes during the copy.
2. Saves the parked Azure database to a file in `~/.cashflow-park/backups`.
3. Recreates the Azure database empty, with the free offer and the same settings as `main.bicep`,
   and copies your Mac's database into it, checked the same way as parking. If the check fails it
   stops; fix the cause and run `up` again (an empty Azure database is reused).
4. Uploads the statement PDFs you added while parked.
5. Moves the backup jobs back to nightly and monthly, sets `AZURE_PARKED=false`, starts the app
   and runs a deploy of `main`, which also brings the database up to date if the code moved on.
   The app may restart a few times until that deploy finishes.

Then put Claude's connection back to the cloud address and token, and run `backfill()` once in
the Gmail script for the statements that arrived meanwhile. To keep the database from ever billing,
run `up` with `LIMIT_WHEN_UP=AutoPause` (the app then stops for the rest of a month once the free
allowance is used).

## Where things are

- `./infra/local/park.sh status`: parked or not, the app's state, the database's state, the
  local containers and the latest saved copies.
- `~/.cashflow-park/backups`: every copy the script made, with its manifest. They hold the whole
  household history: keep the folder off iCloud, Dropbox or any synced folder, and delete old ones
  when you're done with them.
- The local database lives in Docker (`docker compose down -v` removes it, with the local PDFs).
- Azure also keeps its own 7-day point-in-time restore and, when not parked, the nightly backups
  in Blob storage (docs/runbooks/backups.md).
