#!/usr/bin/env bash
# Connect the app to SimpleFIN Bridge (ADR-044): BofA and Capital One movements arrive by
# themselves. Run from the repo root after `az login`; it asks for the setup token without
# echoing it:
#
#   ./infra/azure/setup-simplefin.sh
#
# The setup token works once: this claims it, and the access URL it returns (read access to the
# connected banks) goes straight into a Container App secret. Neither is printed, stored in the
# database or written to the repo. To disconnect, delete the app's access on bridge.simplefin.org.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"

read -r -s -p "SimpleFIN setup token: " TOKEN; echo
CLAIM=$(printf %s "$TOKEN" | tr -d '[:space:]' | base64 --decode 2>/dev/null || true)
[[ "$CLAIM" == https://* ]] || { echo "That doesn't look like a setup token; copy it again."; exit 1; }

ACCESS=$(curl -fsS -X POST -H "Content-Length: 0" "$CLAIM") || {
  echo "SimpleFIN refused the token: it works once. Make a new one on bridge.simplefin.org."
  exit 1
}
[[ "$ACCESS" == https://* ]] || { echo "Unexpected answer from SimpleFIN."; exit 1; }

# Show which accounts it reaches (names only), so you can check both banks are there.
curl -fsS "${ACCESS}/accounts?balances-only=1" | python3 -c '
import json, sys
data = json.load(sys.stdin)
for a in data.get("accounts", []):
    print("  -", (a.get("org") or {}).get("name", "?"), "·", a.get("name", "?"))
for e in data.get("errors", []):
    print("  ! ", e)
'

az containerapp secret set -g "$RG" -n "$APP" --secrets "simplefin-access=$ACCESS" -o none
az containerapp update -g "$RG" -n "$APP" \
  --set-env-vars SIMPLEFIN_ACCESS_URL=secretref:simplefin-access -o none
REVISION=$(az containerapp show -g "$RG" -n "$APP" --query properties.latestRevisionName -o tsv)
az containerapp revision restart -g "$RG" -n "$APP" --revision "$REVISION" -o none
echo "Done: the app can read those accounts. Movements show up once the sync ships."
