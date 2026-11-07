# ADR-044: Bank sync for BofA and Capital One through SimpleFIN

Status: accepted (setup 0.59.1, Nov 2026; the sync itself follows)

## Context

Phase 3 of the improvement plan. Bank of America and Capital One statements arrive once a month
as PDFs, so a month's US spending is only visible weeks later. SimpleFIN Bridge (a small paid
subscription, chosen by Hernan) reads both banks through MX and serves the movements over one
read-only URL.

## Decision

- Hernan connects the banks on bridge.simplefin.org and makes a setup token.
  `infra/azure/setup-simplefin.sh` claims it once (base64 → claim URL → POST), checks the
  accounts it reaches (names only) and stores the access URL as the Container App secret
  `simplefin-access`, exposed as `SIMPLEFIN_ACCESS_URL`. bootstrap.sh and main.bicep carry it
  through redeploys like the other secrets.
- The token and the access URL are never printed, logged, stored in the database or committed.
- The sync (next change) pulls at most once a day, within SimpleFIN's 24 requests a day and 90
  days per request, into staging for approval like any statement; PDF statements stay the source
  that must tie out.
