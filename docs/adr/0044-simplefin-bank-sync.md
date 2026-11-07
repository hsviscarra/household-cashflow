# ADR-044: Bank sync for BofA and Capital One through SimpleFIN

Status: accepted (setup 0.59.1, sync 0.60.0, Nov 2026)

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
- Migration 0035: `core.account.sync_id` (the SimpleFIN account that feeds it, an opaque id,
  unique when set) and `core.transaction.source` gains `bank_sync`. Downgrade deletes the synced
  lines and drops both.
- Settings → Bank sync lists the accounts SimpleFIN reaches (names and balances) and links each
  to an app account. `GET /api/bank-sync`, `POST /api/bank-sync/run`, `PUT /api/bank-sync/link`.
- The app asks for a sync each time it opens (`run?auto=true`); the server runs it only when the
  last run is 12 hours old, and "Sync now" at most every 30 minutes: two requests a day in normal
  use, well under SimpleFIN's 24. Each run reads the last 45 days (SimpleFIN serves 90 at most).
- Posted movements of linked accounts become lines with source `bank_sync` and status
  `pending`, categorized by the rules (including the person and name actions, ADR-042) and
  followed by the same people, transfer and recurring matching as a statement. Pending movements
  are skipped (their amount can still change). Movements dated inside a loaded statement are
  skipped. The natural key is a hash of the SimpleFIN account and movement ids, so a movement is
  read once.
- Synced lines show in the Review list, Transactions, the cash flow and spending like statement
  lines, so a month's US spending is visible before its statement.
- When a statement is approved, each of its lines takes the place of the synced line on the same
  account with the same amount within 5 days (closest first). Category, person, notes and links
  carry over when they were set by hand (or the statement line has no category); splits, transfer
  notes and invoices are repointed. Synced lines dated inside the statement's lines that matched
  nothing are removed: the statement ties out, so it is complete. Each replacement and removal is
  written to `audit.change_log`, and the counts to the statement's load log.

## Not done

- Statement approval stays the gate for the record; synced lines are not staged for approval
  one by one (that would mean approving every day). A line that never gets a statement (an
  account with no PDFs) stays pending.
