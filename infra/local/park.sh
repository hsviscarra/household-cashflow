#!/usr/bin/env bash
# Park the Azure setup and run the app on this Mac, or bring it back to the cloud (ADR-107).
#
#   ./infra/local/park.sh down     copy Azure's data to this Mac, then park Azure (about $0)
#   ./infra/local/park.sh up       copy this Mac's data back to Azure and turn the cloud on
#   ./infra/local/park.sh status   where things stand
#
# Run from the repo root with Docker Desktop running, signed in with `az login` (as the
# subscription's owner) and `gh auth login`. You type the SQL admin password (from bootstrap.sh,
# in your password manager) when asked; it is never printed or written to disk.
# DRY_RUN=1 prints the Azure and GitHub changes instead of making them.
#
# Parked means: the app is stopped, the backup jobs run once a year instead of nightly, the
# database pauses instead of billing once its free allowance is used, and deploys skip Azure
# (repository variable AZURE_PARKED). Nothing is deleted when parking. Coming back replaces the
# Azure database with this Mac's, after saving the Azure one to a file first.
set -euo pipefail

RG=${RG:-rg-cashflow}
PREFIX=${PREFIX:-cashflow}
APP=${APP:-$PREFIX-app}
DB=${DB:-cashflow}
REPO=${REPO:-hsviscarra/household-cashflow}
SQL_ADMIN=${SQL_ADMIN:-cashflowadmin}
# Copies of the household's whole history: keep this folder out of iCloud, Dropbox and the like.
WORK=${PARK_DIR:-$HOME/.cashflow-park}
EXPORT_CRON='17 8 * * *'   # the nightly backup (backups.bicep)
DRILL_CRON='17 9 2 * *'    # the monthly restore drill
PARKED_CRON='17 8 1 1 *'   # once a year while parked: a parked database needs no backups
LIMIT_WHEN_UP=${LIMIT_WHEN_UP:-BillOverUsage}  # or AutoPause: never bill, stop at the allowance

say() { printf '\n== %s\n' "$*"; }
die() { printf 'park.sh: %s\n' "$*" >&2; exit 1; }
run() {  # an Azure or GitHub change: printed instead of made with DRY_RUN=1
  if [ "${DRY_RUN:-}" = 1 ]; then printf 'DRY RUN: %s\n' "$*"; else "$@"; fi
}
confirm() {
  local answer
  read -r -p "$1 Type '$2' to go on: " answer
  [ "$answer" = "$2" ] || die "stopped; nothing more was changed."
}

preflight() {
  if [ ! -f docker-compose.yml ] || [ ! -f infra/ops/Dockerfile ]; then
    die "run this from the repo root."
  fi
  for tool in az gh docker curl; do
    command -v "$tool" >/dev/null || die "$tool is not installed."
  done
  docker info >/dev/null 2>&1 || die "Docker Desktop isn't running."
  az account show >/dev/null 2>&1 || die "sign in first: az login"
  gh auth status >/dev/null 2>&1 || die "sign in first: gh auth login"
  [ -f .env ] || die "create .env first: cp .env.example .env, then set MSSQL_SA_PASSWORD."
  MSSQL_SA_PASSWORD=$(sed -n 's/^MSSQL_SA_PASSWORD=//p' .env | tail -1)
  [ -n "$MSSQL_SA_PASSWORD" ] || die "set MSSQL_SA_PASSWORD in .env."
  export MSSQL_SA_PASSWORD
  SUB=$(az account show --query name -o tsv)
  SERVER=$(az sql server list -g "$RG" --query "[?starts_with(name, '${PREFIX}-sql-')].name | [0]" -o tsv)
  [ -n "$SERVER" ] || die "no SQL server in $RG (subscription: $SUB)."
  FQDN=$(az sql server show -g "$RG" -n "$SERVER" --query fullyQualifiedDomainName -o tsv)
  STORAGE=$(az storage account list -g "$RG" --query "[0].name" -o tsv)
  PARKED=$(gh variable get AZURE_PARKED --repo "$REPO" 2>/dev/null || echo false)
  mkdir -p "$WORK/backups" && chmod 700 "$WORK"
  echo "Subscription $SUB, resource group $RG, server $SERVER, parked: $PARKED"
}

sql_password() {
  if [ -z "${SQL_PASSWORD:-}" ]; then
    read -r -s -p "SQL admin password for $SQL_ADMIN: " SQL_PASSWORD && echo
  fi
  [ -n "$SQL_PASSWORD" ] || die "the SQL admin password is needed."
  export SQL_PASSWORD
}

# This Mac reaches the Azure database through a firewall rule for its own address, removed on exit.
open_firewall() {
  local ip
  ip=$(curl -fsS https://api.ipify.org) || die "couldn't find this Mac's public address."
  RULE="park-$(whoami | tr -cd 'a-zA-Z0-9-')"
  run az sql server firewall-rule create -g "$RG" -s "$SERVER" -n "$RULE" \
    --start-ip-address "$ip" --end-ip-address "$ip" -o none
  trap close_firewall EXIT
}
close_firewall() {
  run az sql server firewall-rule delete -g "$RG" -s "$SERVER" -n "$RULE" -o none || true
}

local_sql() {
  docker compose up -d --wait sqlserver >/dev/null
  NETWORK=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
    "$(docker compose ps -q sqlserver)" | awk '{print $1}')
}
local_query() {  # one value from the local SQL Server
  SQLCMDPASSWORD=$MSSQL_SA_PASSWORD docker compose exec -T -e SQLCMDPASSWORD sqlserver \
    /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -h -1 -W -b -Q "SET NOCOUNT ON; $1" \
    | tr -d '\r' | head -1
}
local_tables() {
  local_query "IF DB_ID(N'$DB') IS NULL SELECT 0 ELSE SELECT COUNT(*) FROM [$DB].[sys].[tables] WHERE [is_ms_shipped] = 0"
}

# The backup image (sqlpackage and app.ops.backup), built from this checkout. sqlpackage is x64
# only, so it runs emulated on Apple silicon.
ops_image() {
  say "Building the backup image (a few minutes the first time)"
  docker build -q --platform linux/amd64 -t cashflow:local . >/dev/null
  docker build -q --platform linux/amd64 -f infra/ops/Dockerfile \
    --build-arg APP_IMAGE=cashflow:local -t cashflow-ops:local . >/dev/null
}
# side <SOURCE|TARGET> <azure|mac>: which database a backup command reads or writes.
side() {
  if [ "$2" = azure ]; then
    export "$1_SERVER=$FQDN,1433" "$1_USER=$SQL_ADMIN" "$1_PASSWORD=$SQL_PASSWORD" "$1_TRUST_CERT=0"
  else
    export "$1_SERVER=sqlserver,1433" "$1_USER=sa" "$1_PASSWORD=$MSSQL_SA_PASSWORD" "$1_TRUST_CERT=1"
  fi
  export "$1_DATABASE=$DB"
}
# ops <export|copy>: settings pass by name (-e NAME), so passwords never appear in a command line.
ops() {
  local names=() v
  for v in SERVER DATABASE USER PASSWORD TRUST_CERT; do names+=(-e "SOURCE_$v" -e "TARGET_$v"); done
  docker run --rm --platform linux/amd64 --network "$NETWORK" -v "$WORK/backups:/backups" \
    -e BACKUP_DIR=/backups -e TARGET_CREATE "${names[@]}" cashflow-ops:local "$1"
}

app_state() { az containerapp show -g "$RG" -n "$APP" --query properties.runningStatus -o tsv 2>/dev/null; }
app_stop() {
  run az containerapp stop -g "$RG" -n "$APP" -o none 2>/dev/null \
    || run az rest -m post --url "$(az containerapp show -g "$RG" -n "$APP" --query id -o tsv)/stop?api-version=2024-03-01" -o none
}
app_start() {
  run az containerapp start -g "$RG" -n "$APP" -o none 2>/dev/null \
    || run az rest -m post --url "$(az containerapp show -g "$RG" -n "$APP" --query id -o tsv)/start?api-version=2024-03-01" -o none
}
jobs_cron() {  # $1 export cron, $2 drill cron; jobs that don't exist are skipped
  if az containerapp job show -g "$RG" -n "$PREFIX-backup" -o none 2>/dev/null; then
    run az containerapp job update -g "$RG" -n "$PREFIX-backup" --cron-expression "$1" -o none
  fi
  if az containerapp job show -g "$RG" -n "$PREFIX-drill" -o none 2>/dev/null; then
    run az containerapp job update -g "$RG" -n "$PREFIX-drill" --cron-expression "$2" -o none
  fi
}
db_limit() { run az sql db update -g "$RG" -s "$SERVER" -n "$DB" --set "freeLimitExhaustionBehavior=$1" -o none; }

# Statement PDFs: the app keeps them in Blob storage in Azure and in a Docker volume here, under
# the same names. Reading Blob with your sign-in needs a data role, given once if missing.
blob_role() {
  local scope me
  scope=$(az storage account show -g "$RG" -n "$STORAGE" --query id -o tsv)
  me=$(az ad signed-in-user show --query id -o tsv)
  if [ -z "$(az role assignment list --assignee "$me" --scope "$scope" --role 'Storage Blob Data Contributor' --query '[0].id' -o tsv)" ]; then
    echo "Your account needs 'Storage Blob Data Contributor' on $STORAGE to copy the statement PDFs."
    confirm "Give it to yourself now?" yes
    run az role assignment create --assignee "$me" --role 'Storage Blob Data Contributor' --scope "$scope" -o none
    echo "Azure takes a minute or two to apply a new role."; sleep 90
  fi
}
statements_down() {
  say "Copying the statement PDFs to this Mac"
  blob_role
  rm -rf "$WORK/statements" && mkdir -p "$WORK/statements"
  az storage blob download-batch --auth-mode login --account-name "$STORAGE" -s statements \
    -d "$WORK/statements" --no-progress -o none
  docker compose create --build api >/dev/null
  docker compose cp "$WORK/statements/." api:/data/statements
  echo "$(find "$WORK/statements" -type f | wc -l | tr -d ' ') files."
}
statements_up() {
  say "Copying statement PDFs uploaded on this Mac to Azure"
  blob_role
  rm -rf "$WORK/statements-up" && mkdir -p "$WORK/statements-up"
  docker compose cp api:/data/statements/. "$WORK/statements-up"
  local there n=0 key
  there=$(az storage blob list --auth-mode login --account-name "$STORAGE" -c statements \
    --num-results '*' --query '[].name' -o tsv)
  while IFS= read -r -d '' f; do
    key=${f#"$WORK/statements-up/"}
    if ! grep -qxF "$key" <<<"$there"; then
      run az storage blob upload --auth-mode login --account-name "$STORAGE" -c statements \
        -n "$key" -f "$f" --no-progress -o none
      n=$((n + 1))
    fi
  done < <(find "$WORK/statements-up" -type f -print0)
  echo "$n new files uploaded."
}

down() {
  [ "$PARKED" = true ] && die "Azure is already parked. To bring it back: ./infra/local/park.sh up"
  echo "This copies the Azure database and statement PDFs to this Mac, then parks Azure."
  echo "From then on, use the app at http://localhost:8000 only, until you run 'up'."
  confirm "Park Azure?" park
  sql_password
  local_sql
  if [ "$(local_tables)" != 0 ]; then
    echo "This Mac already has a '$DB' database. It is saved to $WORK/backups, then replaced."
    confirm "Replace it?" replace
    ops_image
    side SOURCE mac
    ops export
    local_query "ALTER DATABASE [$DB] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$DB];" >/dev/null
  else
    ops_image
  fi
  open_firewall
  say "Copying the Azure database to this Mac (it wakes the Azure database once)"
  side SOURCE azure
  side TARGET mac
  export TARGET_CREATE=1
  ops copy || die "the copy didn't check out; Azure was not parked."
  unset TARGET_CREATE
  statements_down

  say "Parking Azure"
  run gh variable set AZURE_PARKED --body true --repo "$REPO"
  app_stop
  jobs_cron "$PARKED_CRON" "$PARKED_CRON"
  db_limit AutoPause
  close_firewall; trap - EXIT

  say "Starting the app on this Mac"
  docker compose up -d --build
  cat <<MSG

Parked. The app runs at http://localhost:8000 (docker compose up -d after a restart).
- Claude's household-cashflow connection: in Claude's config, change the cloud /mcp address to
  http://localhost:8000/mcp, with the MCP_TOKEN from .env (docs/runbooks/claude-mcp.md).
- Emailed statements can't reach this Mac: they wait in Gmail. Upload any you need on Import.
- The Azure copy as it was is in $WORK/backups as well; keep that folder private.
To come back: ./infra/local/park.sh up
MSG
}

up() {
  [ "$PARKED" = true ] || die "Azure isn't parked (repository variable AZURE_PARKED)."
  git fetch -q origin main
  if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    echo "This checkout isn't origin/main: the cloud will run main's code on this Mac's data."
    confirm "Go on anyway?" yes
  fi
  echo "This saves the Azure database to $WORK/backups, then REPLACES it with this Mac's"
  echo "database and statement PDFs, and turns the cloud app, backups and deploys back on."
  confirm "Bring Azure back?" unpark
  sql_password
  local_sql
  [ "$(local_tables)" != 0 ] || die "this Mac has no '$DB' database to copy."
  ops_image
  docker compose stop api >/dev/null  # no changes while the copy runs
  open_firewall

  say "Saving the parked Azure database to $WORK/backups"
  local azure_db
  azure_db=$(az sql db show -g "$RG" -s "$SERVER" -n "$DB" --query name -o tsv 2>/dev/null || true)
  if [ -n "$azure_db" ]; then
    side SOURCE azure
    ops export || die "couldn't save the Azure database; nothing was changed."
    say "Recreating the Azure database empty, with the free offer"
    run az sql db delete -g "$RG" -s "$SERVER" -n "$DB" --yes -o none
  fi
  run az sql db create -g "$RG" -s "$SERVER" -n "$DB" -e GeneralPurpose -f Gen5 -c 1 \
    --compute-model Serverless --auto-pause-delay 15 --min-capacity 0.5 --max-size 32GB \
    --backup-storage-redundancy Local --use-free-limit true \
    --free-limit-exhaustion-behavior "$LIMIT_WHEN_UP" -o none

  say "Copying this Mac's database to Azure"
  side SOURCE mac
  side TARGET azure
  ops copy || die "the copy didn't check out. The Azure copy is saved in $WORK/backups; fix and run 'up' again."
  statements_up

  say "Turning the cloud back on"
  jobs_cron "$EXPORT_CRON" "$DRILL_CRON"
  run gh variable set AZURE_PARKED --body false --repo "$REPO"
  app_start
  run gh workflow run deploy.yml --repo "$REPO" --ref main
  close_firewall; trap - EXIT
  docker compose stop >/dev/null
  cat <<MSG

Back in the cloud. A deploy of main is running (gh run watch --repo $REPO); the app answers
once it finishes, in a few minutes.
- Claude's household-cashflow connection: change http://localhost:8000/mcp back to the cloud
  address and token.
- Emailed statements that arrived while parked: run backfill() once in the Gmail script.
- The local copy stays in Docker (docker compose down -v removes it) and in $WORK/backups.
MSG
}

status() {
  say "Azure"
  echo "Parked (AZURE_PARKED): $PARKED"
  echo "App: $(app_state || echo unknown)"
  az sql db show -g "$RG" -s "$SERVER" -n "$DB" \
    --query "{database:name, status:status, freeLimit:freeLimitExhaustionBehavior}" -o table
  say "This Mac"
  docker compose ps --format 'table {{.Service}}\t{{.State}}' 2>/dev/null || true
  find "$WORK/backups/db" -name '*.bacpac' 2>/dev/null | sort | tail -4 || true
}

case "${1:-}" in
  down) preflight; down ;;
  up) preflight; up ;;
  status) preflight; status ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
