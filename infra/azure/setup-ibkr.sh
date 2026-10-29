#!/usr/bin/env bash
# Connect the app to Interactive Brokers' read-only Flex Web Service (F22, ADR-019). Run from the
# repo root after `az login`, once you have created the Flex Query and the token
# (docs/runbooks/ibkr.md):
#
#   ./infra/azure/setup-ibkr.sh
#
# It asks for the Query ID and the token without showing them, stores them as Container App
# secrets, and points the app at them (a new revision). Re-run it when the token is renewed.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"

read -rp "Flex Query ID (the number next to the query in Client Portal): " QUERY_ID
read -rsp "Flex Web Service token (not shown): " TOKEN; echo
[ -n "$QUERY_ID" ] && [ -n "$TOKEN" ] || { echo "Both are needed."; exit 1; }

echo "1/2 Storing them as secrets..."
az containerapp secret set -g "$RG" -n "$APP" \
  --secrets "ibkr-flex-token=$TOKEN" "ibkr-flex-query-id=$QUERY_ID" -o none
az containerapp update -g "$RG" -n "$APP" \
  --set-env-vars IBKR_FLEX_TOKEN=secretref:ibkr-flex-token \
  IBKR_FLEX_QUERY_ID=secretref:ibkr-flex-query-id -o none

echo "2/2 Done. Open Debt & Net Worth: the app reads the portfolio the first time and then once"
echo "a day (or with Refresh from IBKR). Renew the token in Client Portal before it expires and"
echo "run this again."
