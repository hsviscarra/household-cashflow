#!/usr/bin/env bash
# One-time Azure setup for Household Cash Flow. Run from the repo root:
#
#   az login && gh auth login
#   ALERT_EMAIL=you@example.com ALLOWED_EMAILS="you@example.com,lauren@example.com" \
#     ./infra/azure/bootstrap.sh
#
# It creates the resource group and resources (infra/azure/main.bicep), the sign-in
# app registration for Microsoft personal accounts, and a GitHub OIDC identity that
# lets deploy.yml roll new images without stored cloud secrets. Safe to re-run.
set -euo pipefail

: "${ALERT_EMAIL:?set ALERT_EMAIL}"
: "${ALLOWED_EMAILS:?set ALLOWED_EMAILS (comma-separated)}"
LOCATION="${LOCATION:-eastus2}"
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

az group create -n "$RG" -l "$LOCATION" -o none

# Keep the SQL password stable across re-runs: reuse it if the app already holds it.
SQL_PASSWORD="${SQL_PASSWORD:-}"
if [ -z "$SQL_PASSWORD" ]; then
  SQL_PASSWORD="Cf-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)-9a!"
  NEW_PASSWORD=1
fi

deploy() {
  az deployment group create -g "$RG" -n cashflow -f infra/azure/main.bicep \
    -p prefix="$PREFIX" sqlAdminPassword="$SQL_PASSWORD" allowedEmails="$ALLOWED_EMAILS" \
       ghcrUsername="$GH_USER" ghcrToken="$GHCR_TOKEN" alertEmail="$ALERT_EMAIL" "$@" \
    --query properties.outputs -o json
}

echo "1/4 Deploying resources (no sign-in yet)..."
OUT=$(deploy enableAuth=false)
APP=$(echo "$OUT" | jq -r .appName.value)
FQDN=$(echo "$OUT" | jq -r .fqdn.value)

echo "2/4 Sign-in app registration for https://$FQDN ..."
AUTH_APP_ID=$(az ad app list --display-name "$PREFIX-signin" --query "[0].appId" -o tsv)
if [ -z "$AUTH_APP_ID" ]; then
  AUTH_APP_ID=$(az ad app create --display-name "$PREFIX-signin" \
    --sign-in-audience AzureADandPersonalMicrosoftAccount \
    --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" \
    --enable-id-token-issuance true --query appId -o tsv)
fi
AUTH_SECRET=$(az ad app credential reset --id "$AUTH_APP_ID" --display-name containerapp \
  --years 2 --query password -o tsv --only-show-errors)

echo "3/4 Redeploying with sign-in on..."
deploy enableAuth=true authClientId="$AUTH_APP_ID" authClientSecret="$AUTH_SECRET" >/dev/null

echo "4/4 GitHub OIDC deploy identity..."
DEPLOY_APP_ID=$(az ad app list --display-name "$PREFIX-github-deploy" --query "[0].appId" -o tsv)
if [ -z "$DEPLOY_APP_ID" ]; then
  DEPLOY_APP_ID=$(az ad app create --display-name "$PREFIX-github-deploy" --query appId -o tsv)
  az ad sp create --id "$DEPLOY_APP_ID" -o none
fi
# deploy.yml runs in the "production" environment, so the token subject names it. GitHub may send
# the name-based subject or the newer ID-based one (owner@id/repo@id); trust both.
OWNER_ID=$(gh api "repos/$REPO" --jq .owner.id)
REPO_ID=$(gh api "repos/$REPO" --jq .id)
add_subject() {
  local name="$1" subject="$2"
  if ! az ad app federated-credential list --id "$DEPLOY_APP_ID" --query "[?subject=='$subject'] | [0].name" -o tsv | grep -q .; then
    az ad app federated-credential create --id "$DEPLOY_APP_ID" --parameters "{
      \"name\": \"$name\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$subject\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" -o none
  fi
}
add_subject github-production "repo:$REPO:environment:production"
add_subject github-production-ids "repo:${REPO%%/*}@$OWNER_ID/${REPO#*/}@$REPO_ID:environment:production"
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
