#!/usr/bin/env bash
# Rotate the Azure SQL admin password and update the app's DATABASE_URL secret in one step,
# then restart the app so it reconnects. Run from the repo root:  bash infra/azure/rotate-sql-password.sh
# Prints the new password once at the end: save it in your password manager.
set -euo pipefail

RG="${RG:-rg-cashflow}"
APP="${APP:-cashflow-app}"
LOGIN="${LOGIN:-cashflowadmin}"

NEW="Cf-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)-9a!"
SQL=$(az sql server list -g "$RG" --query "[0].name" -o tsv)
FQDN=$(az sql server show -g "$RG" -n "$SQL" --query fullyQualifiedDomainName -o tsv)
ENC=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$NEW")
URL="mssql+pyodbc://${LOGIN}:${ENC}@${FQDN}:1433/cashflow?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&Connection+Timeout=60"

echo "Updating SQL admin password on ${SQL}..."
az sql server update -g "$RG" -n "$SQL" --admin-password "$NEW" -o none
echo "Updating the app's database-url secret..."
az containerapp secret set -g "$RG" -n "$APP" --secrets "database-url=$URL" -o none
REV=$(az containerapp revision list -g "$RG" -n "$APP" --query "[?properties.active] | [0].name" -o tsv)
echo "Restarting revision ${REV}..."
az containerapp revision restart -g "$RG" -n "$APP" --revision "$REV" -o none

echo
echo "Done. New SQL admin password (save it in your password manager, do not share it):"
echo "$NEW"
