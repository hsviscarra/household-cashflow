#!/usr/bin/env bash
# Add "Sign in with Google" next to Microsoft (ADR-083). Run from the repo root after `az login`:
#
#   GOOGLE_CLIENT_ID=...apps.googleusercontent.com ./infra/azure/setup-google-signin.sh
#
# It asks for the client secret without showing it (or reads GOOGLE_CLIENT_SECRET), keeps it as a
# Container App secret, adds Google to the sign-in in front of the app, and makes Google the
# provider people are sent to. Microsoft keeps working at /.auth/login/aad.
#
# Before running it, create the Google client once (docs/runbooks/google-sign-in.md): Google Cloud
# console -> APIs & Services -> Credentials -> OAuth client ID -> Web application, with the
# redirect URI this script prints when run with no client id.
#
# The Gmail addresses that may sign in must be in ALLOWED_EMAILS; pass any that are missing:
#   GOOGLE_EMAILS="a@gmail.com,b@gmail.com"
# DEFAULT_PROVIDER=azureactivedirectory keeps Microsoft as the one people are sent to.
# Safe to re-run (a new secret replaces the old one).
set -euo pipefail

RG="${RG:-rg-cashflow}"
PREFIX="${PREFIX:-cashflow}"
APP="${PREFIX}-app"
DEFAULT_PROVIDER="${DEFAULT_PROVIDER:-google}"

APP_ID=$(az containerapp show -g "$RG" -n "$APP" --query id -o tsv)
FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
echo "Redirect URI for the Google client: https://$FQDN/.auth/login/google/callback"
if [ -z "${GOOGLE_CLIENT_ID:-}" ]; then
  echo "Set GOOGLE_CLIENT_ID (and run again) once the Google client exists."
  exit 0
fi
if [ -z "${GOOGLE_CLIENT_SECRET:-}" ]; then
  read -rsp "Google client secret (not shown): " GOOGLE_CLIENT_SECRET
  echo
fi
[ -n "$GOOGLE_CLIENT_SECRET" ] || { echo "No secret given."; exit 1; }

echo "1/3 Secret..."
az containerapp secret set -g "$RG" -n "$APP" \
  --secrets "google-provider-secret=$GOOGLE_CLIENT_SECRET" -o none

echo "2/3 Sign-in: adding Google, sending people to $DEFAULT_PROVIDER..."
URL="https://management.azure.com${APP_ID}/authConfigs/current?api-version=2024-03-01"
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT
az rest -m get --url "$URL" -o json | GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
  DEFAULT_PROVIDER="$DEFAULT_PROVIDER" python3 -c '
import json, os, sys
cfg = json.load(sys.stdin)
p = cfg["properties"]
p.setdefault("identityProviders", {})["google"] = {
    "enabled": True,
    "registration": {
        "clientId": os.environ["GOOGLE_CLIENT_ID"],
        "clientSecretSettingName": "google-provider-secret",
    },
    "login": {"scopes": ["openid", "email", "profile"]},
}
p.setdefault("globalValidation", {})["redirectToProvider"] = os.environ["DEFAULT_PROVIDER"]
json.dump({"properties": p}, sys.stdout)
' > "$BODY"
az rest -m put --url "$URL" --body @"$BODY" -o none

echo "3/3 Allowed accounts..."
if [ -n "${GOOGLE_EMAILS:-}" ]; then
  NOW=$(az containerapp show -g "$RG" -n "$APP" \
    --query "properties.template.containers[0].env[?name=='ALLOWED_EMAILS'].value | [0]" -o tsv)
  ALL=$(printf '%s,%s' "$NOW" "$GOOGLE_EMAILS" | tr ',' '\n' | tr '[:upper:]' '[:lower:]' \
    | sed 's/ //g' | grep -v '^$' | sort -u | paste -sd, -)
  az containerapp update -g "$RG" -n "$APP" --set-env-vars "ALLOWED_EMAILS=$ALL" -o none
  echo "Allowed: $(echo "$ALL" | tr ',' '\n' | wc -l | tr -d ' ') accounts."
else
  echo "Unchanged. A Gmail address that isn't allowed yet gets \"This account is not allowed\":"
  echo "run again with GOOGLE_EMAILS=\"address@gmail.com\"."
fi

echo
echo "Done. Open https://$FQDN in a private window: it goes to Google."
echo "Microsoft still works: https://$FQDN/.auth/login/aad?post_login_redirect_uri=/"
echo "Sign out of either: https://$FQDN/.auth/logout"
