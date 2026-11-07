#!/usr/bin/env bash
# Tell the app whose invoice is whose (ADR-036): the buyer's ID on each SRI invoice is compared
# with these while the XML is read, and only the name is stored. Run from the repo root after
# `az login`; it asks for each cédula without echoing it:
#
#   ./infra/azure/setup-buyers.sh
#
# The IDs live only in this Container App secret, never in the database or the repo.
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"

read -r -s -p "Hernan's cédula: " HERNAN; echo
read -r -s -p "Lauren's cédula: " LAUREN; echo
for id in "$HERNAN" "$LAUREN"; do
  [[ "$id" =~ ^[0-9]{10}$ ]] || { echo "A cédula is 10 digits."; exit 1; }
done

az containerapp secret set -g "$RG" -n "$APP" \
  --secrets "invoice-buyers=Hernan:$HERNAN,Lauren:$LAUREN" -o none
az containerapp update -g "$RG" -n "$APP" \
  --set-env-vars INVOICE_BUYERS=secretref:invoice-buyers -o none
echo "Done: new invoices are assigned to Hernan or Lauren as they arrive."
echo "Invoices already in the app keep their person; choose it on Gastos personales."
