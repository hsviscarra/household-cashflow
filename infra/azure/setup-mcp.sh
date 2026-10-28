#!/usr/bin/env bash
# Turn on Claude's read-only MCP endpoint (F18, ADR-017) on the deployed app and print the Claude
# desktop app's configuration. Run from the repo root after `az login`:
#
#   ./infra/azure/setup-mcp.sh
#
# It creates (or keeps) two secrets on the Container App: the endpoint's bearer token and the
# password of the read-only database login, which the app creates at start-up. It lets /mcp past
# the sign-in (the token protects it instead), then checks the endpoint answers. Safe to re-run:
# the token is kept unless ROTATE=1.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"

secret() {
  az containerapp secret show -g "$RG" -n "$APP" --secret-name "$1" --query value -o tsv \
    2>/dev/null || true
}

TOKEN="$(secret mcp-token)"
if [ -z "$TOKEN" ] || [ "${ROTATE:-0}" = 1 ]; then
  TOKEN="$(openssl rand -hex 32)"
fi
READER_PASSWORD="$(secret reader-password)"
if [ -z "$READER_PASSWORD" ]; then
  READER_PASSWORD="Rd-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)-7a!"
fi

echo "1/3 Secrets and settings (a new revision creates the read-only login)..."
az containerapp secret set -g "$RG" -n "$APP" \
  --secrets "mcp-token=$TOKEN" "reader-password=$READER_PASSWORD" -o none
az containerapp update -g "$RG" -n "$APP" \
  --set-env-vars MCP_TOKEN=secretref:mcp-token READER_PASSWORD=secretref:reader-password -o none

echo "2/3 Letting /mcp past the sign-in (it checks the token instead)..."
az containerapp auth update -g "$RG" -n "$APP" --excluded-paths "/api/health,/mcp" -o none

FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
URL="https://$FQDN/mcp"

echo "3/3 Checking the endpoint (the app and the database may take a minute to wake up)..."
BODY='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
for i in $(seq 1 18); do
  CODE=$(curl -s -o /tmp/mcp-check.json -w '%{http_code}' -X POST "$URL" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" -d "$BODY" || true)
  if [ "$CODE" = 200 ] && grep -q compare_months /tmp/mcp-check.json; then
    echo "    $URL answers with the household's tools."
    break
  fi
  echo "    attempt $i: HTTP $CODE"
  [ "$i" = 18 ] && { echo "The endpoint didn't answer; see the app's logs."; exit 1; }
  sleep 10
done
rm -f /tmp/mcp-check.json

cat <<CONFIG

Done. In the Claude desktop app: Settings -> Developer -> Edit Config, and add this to
claude_desktop_config.json (inside "mcpServers" if the file already has it), then restart Claude.
It needs Node.js (brew install node). Keep the token private: it reads all the household's
numbers. To replace it later: ROTATE=1 ./infra/azure/setup-mcp.sh

{
  "mcpServers": {
    "household-cashflow": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.1", "$URL", "--header", "Authorization:\${MCP_AUTH}"],
      "env": { "MCP_AUTH": "Bearer $TOKEN" }
    }
  }
}
CONFIG
