#!/usr/bin/env bash
# Cost guard (ADR-076): a $20 monthly cap with emails, a cost anomaly alert, and a kill switch that
# stops the app at $20. Run from the repo root, signed in as the subscription's owner (it assigns a
# role to the kill switch and creates a subscription budget, which the deploy identity can't):
#
#   az login
#   ALERT_EMAIL=you@example.com ./infra/azure/setup-cost-guard.sh
#
# Safe to re-run; re-run it once a year to renew the anomaly alert. AMOUNT=30 changes the cap.
#
# After the kill switch fires (you get an email saying the budget reached 100%), the app is stopped
# and the database pauses instead of billing once its free allowance is used. To turn everything
# back on, knowing it may cost more this month:
#
#   ./infra/azure/setup-cost-guard.sh --restart
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
AMOUNT="${AMOUNT:-20}"
APP="${PREFIX}-app"

if [ "${1:-}" = "--restart" ]; then
  SQL=$(az sql server list -g "$RG" --query "[?starts_with(name, '${PREFIX}-sql-')].name | [0]" -o tsv)
  echo "Database $SQL/cashflow: bill past the free allowance again (ADR-046)..."
  az sql db update -g "$RG" -s "$SQL" -n cashflow \
    --set properties.freeLimitExhaustionBehavior=BillOverUsage -o none
  echo "Starting $APP..."
  az containerapp start -g "$RG" -n "$APP" -o none 2>/dev/null \
    || az rest -m post --url "$(az containerapp show -g "$RG" -n "$APP" --query id -o tsv)/start?api-version=2024-03-01" -o none
  echo "Running: https://$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)"
  exit 0
fi

: "${ALERT_EMAIL:?set ALERT_EMAIL}"
SUB_ID=$(az account show --query id -o tsv)
LOCATION=$(az group show -n "$RG" --query location -o tsv)

# Azure won't change a budget's start date, so a budget that exists keeps its own.
started() {
  az rest -m get --url "https://management.azure.com$1/providers/Microsoft.Consumption/budgets/$2?api-version=2023-11-01" \
    --query "properties.timePeriod.startDate" -o tsv 2>/dev/null | cut -c1-10
}
RG_START=$(started "/subscriptions/$SUB_ID/resourceGroups/$RG" "$PREFIX-budget" || true)
SUB_START=$(started "/subscriptions/$SUB_ID" "$PREFIX-subscription-budget" || true)

echo "1/2 Resource group $RG: \$$AMOUNT budget, emails at 25/50/80/100% and forecast, kill switch..."
az deployment group create -g "$RG" -n cashflow-cost-guard -f infra/azure/cost-guard.bicep \
  -p prefix="$PREFIX" alertEmail="$ALERT_EMAIL" amount="$AMOUNT" \
     ${RG_START:+budgetStartDate="$RG_START"} -o none

echo "2/2 Subscription $SUB_ID: \$$AMOUNT budget and cost anomaly alert..."
az deployment sub create -l "$LOCATION" -n cashflow-cost-guard-sub \
  -f infra/azure/cost-guard-sub.bicep \
  -p prefix="$PREFIX" alertEmail="$ALERT_EMAIL" amount="$AMOUNT" \
     ${SUB_START:+budgetStartDate="$SUB_START"} -o none

echo
echo "Done. Budgets:"
az consumption budget list --query "[].{name:name, amount:amount}" -o table 2>/dev/null || true
az consumption budget list -g "$RG" --query "[].{name:name, amount:amount}" -o table 2>/dev/null || true
echo "Test the kill switch only if you want the app stopped now:"
echo "  curl -sX POST \"\$(az rest -m post --url https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Logic/workflows/$PREFIX-kill-switch/triggers/manual/listCallbackUrl?api-version=2019-05-01 --query value -o tsv)\" -H Content-Type:application/json -d {}"
echo "  then: ./infra/azure/setup-cost-guard.sh --restart"
