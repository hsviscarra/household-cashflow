# ADR-026: Personal settings, the person switch and saved views

Status: accepted (0.42.0, Nov 2026)

## Context

The redesign's second PR (see ADR-025). Hernan and Lauren use the same app for different things:
each wants to see their own lines, pick the columns they care about and keep a few views they
open often, on the laptop and on the phone. Until now nothing was remembered, and no page could
show one person's lines except the drill-down on Spending.

## Decision

- **`core.user_setting`** (migration 0029): one row per signed-in person and key, the value as
  JSON the web app owns. The person is the sign-in email Container Apps passes on
  (`X-MS-CLIENT-PRINCIPAL-NAME`), or "local" without sign-in. No financial data; the read-only
  login can't read it. Keys are short names (`person`, `density`, `table:transactions`,
  `views`), at most 100 per person and 20,000 characters each.
- **`/api/me/settings`**: GET returns the person's settings, PUT `/{key}` saves one, DELETE
  removes one. Each person only ever reads and writes their own. The existing `/api/me` (who is
  signed in) is unchanged.
- **Both / Hernan / Lauren switch** at the top of the sidebar, saved per person. Spending and
  Transactions follow it now (`person=` on `/api/spending` and `/api/transactions`; "Joint" also
  takes lines with no person); a note on the page says when only one person's lines show, with
  a "Show both" link. The other pages follow it in their own redesign PRs.
- **Row size** (comfortable or compact) is one choice for every table, applied from `<html
  data-density>`. **Columns** are chosen per table, starting with Transactions (date, account,
  who, category; the description and amount always show).
- **Saved views**: "Save view" on Transactions and Spending keeps the page's filters and who it
  shows under a name, listed in the sidebar; the month is left out unless asked, so "Lauren to
  sort" always opens the current month. Transactions gains a search box and a "Needs a category"
  filter so views have something to keep.
- Pages wait for the settings before loading, so a filtered page loads once, already filtered.

## Consequences

- Home widgets (choosing and ordering Home's tiles) move to the Home and Cash flow PR, where
  Home is rebuilt.
- More tables get a column chooser as their pages are redesigned; row size already applies to
  all of them.
- Settings are not part of the backup export; they are preferences, quick to set again.
