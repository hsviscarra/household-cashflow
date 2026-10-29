#!/usr/bin/env bash
# Turn on the statement inbox (F20, ADR-020): the endpoint the Gmail script posts statement PDFs
# to. Run from the repo root after `az login`:
#
#   ./infra/azure/setup-inbox.sh
#
# It creates (or keeps) the inbox token as a Container App secret, lets /api/inbox past the
# sign-in (the token protects it instead), checks the endpoint answers, and prints the two values
# to paste into the Gmail script's Script properties (docs/runbooks/gmail-statements.md).
# Safe to re-run: the token is kept unless ROTATE=1.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"

secret() {
  az containerapp secret show -g "$RG" -n "$APP" --secret-name "$1" --query value -o tsv \
    2>/dev/null || true
}

TOKEN="$(secret inbox-token)"
if [ -z "$TOKEN" ] || [ "${ROTATE:-0}" = 1 ]; then
  TOKEN="$(openssl rand -hex 32)"
fi

echo "1/3 Secret and setting..."
az containerapp secret set -g "$RG" -n "$APP" --secrets "inbox-token=$TOKEN" -o none
az containerapp update -g "$RG" -n "$APP" --set-env-vars INBOX_TOKEN=secretref:inbox-token -o none

echo "2/3 Letting /api/inbox past the sign-in (it checks the token instead)..."
EXCLUDED="/api/health,/api/inbox"
if [ -n "$(secret mcp-token)" ]; then EXCLUDED="$EXCLUDED,/mcp"; fi
az containerapp auth update -g "$RG" -n "$APP" --excluded-paths "$EXCLUDED" -o none

FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
URL="https://$FQDN"

echo "3/3 Checking the endpoint (the app and the database may take a minute to wake up)..."
for i in $(seq 1 18); do
  # No file on purpose: 422 means the token was accepted and nothing was stored.
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/api/inbox" \
    -H "Authorization: Bearer $TOKEN" || true)
  if [ "$CODE" = 422 ]; then
    echo "    $URL/api/inbox accepts the token."
    break
  fi
  echo "    attempt $i: HTTP $CODE"
  [ "$i" = 18 ] && { echo "The endpoint didn't answer; see the app's logs."; exit 1; }
  sleep 10
done

cat <<PROPS

Done. In the Gmail script (script.google.com -> your project -> Project Settings -> Script
properties) add these two, then run setup() once (docs/runbooks/gmail-statements.md):

  APP_URL      $URL
  INBOX_TOKEN  $TOKEN

Keep the token private: it lets anyone post files to the inbox (they still wait for your approval).
To replace it later: ROTATE=1 ./infra/azure/setup-inbox.sh, then update INBOX_TOKEN in the script.
PROPS
