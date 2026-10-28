#!/usr/bin/env bash
# One-time setup of the nightly backup and the monthly restore drill (F17, ADR-016), next to the
# resources bootstrap.sh created. Doesn't touch the app. Run from the repo root, signed in as the
# subscription's owner (it assigns a role and sets the SQL server's Microsoft Entra admin):
#
#   az login
#   ./infra/azure/setup-backups.sh
#
# Needs the backup image, which deploy.yml builds on every merge to main. At the end it runs one
# backup and one restore drill and prints their results. Safe to re-run.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
GH_USER="${REPO%%/*}"
IMAGE="${IMAGE:-ghcr.io/${REPO}-ops:latest}"
APP="${PREFIX}-app"

# The same read:packages token the app pulls its image with.
GHCR_TOKEN=$(az containerapp secret show -g "$RG" -n "$APP" --secret-name ghcr-token \
  --query value -o tsv)

echo "1/3 Backup identity, SQL Entra admin, retention, jobs ($IMAGE)..."
OUT=$(az deployment group create -g "$RG" -n cashflow-backups -f infra/azure/backups.bicep \
  -p prefix="$PREFIX" image="$IMAGE" ghcrUsername="$GH_USER" ghcrToken="$GHCR_TOKEN" \
  --query properties.outputs -o json)
EXPORT_JOB=$(echo "$OUT" | jq -r .exportJob.value)
DRILL_JOB=$(echo "$OUT" | jq -r .drillJob.value)
gh variable set AZURE_BACKUP_JOBS --repo "$REPO" --body "$EXPORT_JOB $DRILL_JOB"

run() {
  local job="$1" name status
  name=$(az containerapp job start -g "$RG" -n "$job" --query name -o tsv)
  echo "    started $name"
  for _ in $(seq 1 120); do
    status=$(az containerapp job execution show -g "$RG" -n "$job" --job-execution-name "$name" \
      --query properties.status -o tsv)
    case "$status" in
      Succeeded) echo "    $job: Succeeded"; return 0 ;;
      Failed|Stopped|Degraded) echo "    $job: $status"; return 1 ;;
    esac
    sleep 15
  done
  echo "    $job: still running after 30 minutes"; return 1
}

echo "2/3 First backup (the identity's role can take a few minutes to apply; retrying)..."
for attempt in 1 2 3; do
  if run "$EXPORT_JOB"; then break; fi
  [ "$attempt" = 3 ] && { echo "Backup failed: see the job's logs in the portal."; exit 1; }
  sleep 120
done

echo "3/3 Restore drill into a throwaway SQL Server..."
run "$DRILL_JOB" || { echo "Drill failed: see Data Status in the app and the job's logs."; exit 1; }

echo
echo "Done. Backups run nightly at 03:17 (Quito) and are kept 30 days; the restore drill runs on"
echo "the 2nd of each month. The app's Data Status page shows the last backup and drill."
