#!/usr/bin/env bash
# One-time Azure setup for Household Cash Flow. Run from the repo root:
#
#   az login && gh auth login
#   ALERT_EMAIL=you@example.com ALLOWED_EMAILS="you@example.com,lauren@example.com" \
#     LOCATION=eastus ./infra/azure/bootstrap.sh
#
# LOCATION is the Azure region (default eastus). If Azure SQL says a region is not accepting
# new servers, delete the resource group and re-run with another region (e.g. centralus).
#
# It creates the resource group and resources (infra/azure/main.bicep), the sign-in
# app registration for Microsoft personal accounts, and a GitHub OIDC identity that
# lets deploy.yml roll new images without stored cloud secrets. Safe to re-run.
set -euo pipefail

: "${ALERT_EMAIL:?set ALERT_EMAIL}"
: "${ALLOWED_EMAILS:?set ALLOWED_EMAILS (comma-separated)}"
LOCATION="${LOCATION:-eastus}"
RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
GH_USER="${REPO%%/*}"

if [ -z "${GHCR_TOKEN:-}" ]; then
  echo "GitHub classic token with only read:packages (github.com/settings/tokens):"
  read -rs GHCR_TOKEN; echo
fi

SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Subscription $SUB_ID, resource group $RG in $LOCATION, repo $REPO"

# Resource providers must be registered once per subscription before first use.
for ns in Microsoft.App Microsoft.Sql Microsoft.Storage Microsoft.Consumption; do
  state=$(az provider show -n "$ns" --query registrationState -o tsv 2>/dev/null || echo NotRegistered)
  if [ "$state" != "Registered" ]; then
    echo "Registering $ns (one time, can take a few minutes)…"
    az provider register -n "$ns" --wait -o none
  fi
done

EXISTING_LOCATION=$(az group show -n "$RG" --query location -o tsv 2>/dev/null || true)
if [ -n "$EXISTING_LOCATION" ] && [ "$EXISTING_LOCATION" != "$LOCATION" ]; then
  echo "Resource group $RG already exists in $EXISTING_LOCATION, not $LOCATION."
  echo "Delete it first if it only holds a failed attempt:  az group delete -n $RG --yes"
  exit 1
fi
az group create -n "$RG" -l "$LOCATION" -o none

# Keep the SQL password stable across re-runs: reuse it if the app already holds it.
SQL_PASSWORD="${SQL_PASSWORD:-}"
if [ -z "$SQL_PASSWORD" ]; then
  SQL_PASSWORD="Cf-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)-9a!"
  NEW_PASSWORD=1
fi

deploy() {
  az deployment group create -g "$RG" -n cashflow -f infra/azure/main.bicep \
    -p location="$LOCATION" prefix="$PREFIX" sqlAdminPassword="$SQL_PASSWORD" allowedEmails="$ALLOWED_EMAILS" \
       ghcrUsername="$GH_USER" ghcrToken="$GHCR_TOKEN" alertEmail="$ALERT_EMAIL" "$@" \
    --query properties.outputs -o json
}

echo "1/4 Deploying resources (no sign-in yet)…"
OUT=$(deploy enableAuth=false)
APP=$(echo "$OUT" | jq -r .appName.value)
FQDN=$(echo "$OUT" | jq -r .fqdn.value)

echo "2/4 Sign-in app registration for https://$FQDN …"
AUTH_APP_ID=$(az ad app list --display-name "$PREFIX-signin" --query "[0].appId" -o tsv)
if [ -z "$AUTH_APP_ID" ]; then
  AUTH_APP_ID=$(az ad app create --display-name "$PREFIX-signin" \
    --sign-in-audience AzureADandPersonalMicrosoftAccount \
    --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" \
    --enable-id-token-issuance true --query appId -o tsv)
fi
AUTH_SECRET=$(az ad app credential reset --id "$AUTH_APP_ID" --display-name containerapp \
  --years 2 --query password -o tsv --only-show-errors)

echo "3/4 Redeploying with sign-in on…"
deploy enableAuth=true authClientId="$AUTH_APP_ID" authClientSecret="$AUTH_SECRET" >/dev/null

echo "4/4 GitHub OIDC deploy identity…"
DEPLOY_APP_ID=$(az ad app list --display-name "$PREFIX-github-deploy" --query "[0].appId" -o tsv)
if [ -z "$DEPLOY_APP_ID" ]; then
  DEPLOY_APP_ID=$(az ad app create --display-name "$PREFIX-github-deploy" --query appId -o tsv)
  az ad sp create --id "$DEPLOY_APP_ID" -o none
  # deploy.yml runs in the "production" environment, so the token subject names it.
  az ad app federated-credential create --id "$DEPLOY_APP_ID" --parameters "{
    \"name\": \"github-production\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:$REPO:environment:production\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi
az role assignment create --assignee "$DEPLOY_APP_ID" --role Contributor \
  --scope "/subscriptions/$SUB_ID/resourceGroups/$RG" -o none 2>/dev/null || true

gh api -X PUT "repos/$REPO/environments/production" >/dev/null
for kv in "AZURE_CLIENT_ID=$DEPLOY_APP_ID" "AZURE_TENANT_ID=$TENANT_ID" \
          "AZURE_SUBSCRIPTION_ID=$SUB_ID" "AZURE_RG=$RG" "AZURE_APP_NAME=$APP"; do
  gh variable set "${kv%%=*}" --repo "$REPO" --body "${kv#*=}"
done

echo
echo "Done. App: https://$FQDN (shows a placeholder until the first deploy from main)."
if [ "${NEW_PASSWORD:-0}" = 1 ]; then
  echo "SQL admin password (save it in your password manager; needed to re-run this script"
  echo "as SQL_PASSWORD=... and for direct database access): $SQL_PASSWORD"
fi
