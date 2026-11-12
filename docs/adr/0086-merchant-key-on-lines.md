# ADR-086: The merchant key is stored on each line

Status: accepted (0.95.0, Nov 2026). Hernan approved the schema change on Nov 12 2026.

To do is asked for on every page (its count is in the menu) and again after every action. A
profile on 15,000 synthetic lines showed where building it went: 89% in the Suggestions section,
which read every hand-categorized line and every expense of the last 400 days as full rows and
ran the merchant-key regular expressions on each (16,000 times a build), and then asked for the
lines behind each steady charge one query at a time.

## Decision

- `core.transaction.merchant_key` (NVARCHAR(200), indexed) holds `rules.key(description_raw)`.
  Migration 0052 adds it and fills the lines already loaded with the app's own function; its
  downgrade drops the index and the column.
- A `before_flush` hook in `app.models` sets it for every new line and whenever a description
  changes, so no loader has to remember. Nothing writes lines outside the ORM.
- Rule suggestions and rule learning group and filter by the column in SQL; only the lines of
  merchants that qualify are read.
- Subscriptions read the eight columns they use instead of whole rows, and take the stored key.
  Found bills read the lines behind the steady charges in one query, not one each.
- To do asks for the transfers that don't say who once, not twice.

## Consequences

- On the same synthetic database a build went from 0.65 s to 0.19 s and from 823,000 function
  calls to 94,000. On Azure SQL the saving is larger than that ratio, since the rows no longer
  cross the network.
- If `rules.key` ever changes, a migration must recompute the column; the function's docstring
  and this ADR say so.
- Not done: a count-only request for the menu. With the scans gone the count costs the same as
  the list (every section must still be evaluated), so it would add an endpoint and save nothing.
