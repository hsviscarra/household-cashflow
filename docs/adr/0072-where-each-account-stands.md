# ADR-072: Where each account stands, and bank sync instead of PDFs

Status: accepted (0.81.0, Nov 2026)

## Context

Hernan, Nov 11 2026: he wants one table of everything pending, what arrives on its own and is
still on its way, and what he must upload, checked at least once a day; and since Capital One and
Bank of America sync daily, the app should stop asking for their PDFs.

## Decision

- `status.sync_coverage`: an account linked to bank sync (ADR-044) counts as covered from its
  first synced line to the last sync, or to today while that sync is at most 3 days old. Data
  Status no longer lists those accounts' PDFs as missing; the statement timeline shows the synced
  span as "Bank sync".
- `status.sources`: one row per open account: how its data arrives (bank sync; email through the
  Gmail script for Pichincha, PacifiCard and Diners; upload for the rest), the last day it covers,
  and its state: late, waiting on you, on Import, on its way, or up to date. An emailed statement
  is on its way until 7 days after it closes, then late ("check the Gmail script"). It is on the
  Data Status page ("Where each account stands"), in `GET /api/status` and in Claude's
  `data_status` tool.
- The monthly reminder becomes a daily check that reads it and notifies only when something is
  late or waiting on Hernan.
- Migration 0048 sets Lauren's Diners opening to September 2026.

## Consequences

Synced accounts' PDFs can still be uploaded and still load; they are just no longer expected.
