# ADR-030: Transactions you can slice, save and export; people linked to their lines

Status: accepted (0.46.0, Nov 2026)

## Context

The redesign's sixth PR (ADR-025). Transactions showed one month with a search box. Finding
"everything over $500 on Lauren's cards" or "a year of Rubén" meant scrolling, and People showed
a person's lines in a short list with no way to filter or export them.

## Decision

- **Filters**, all in the address (so a view can be saved): month and **period** (this month,
  3 or 12 months up to it), **account**, **category group**, **amount** range (without sign),
  **has a note**, needs a category, and search on description, merchant, note, category,
  account or amount ("191.10", "$80").
- **Saved views as tabs** above the filters: "All" and every view saved on this page; the
  current one is marked, and opening one also sets the Both/Hernan/Lauren switch it was saved
  with. Views stay listed in the sidebar too (ADR-026).
- **Columns**: date, account, who, category and a new **note / person** column by default;
  **merchant (cleaned)**, **posted date** and **country** can be added. The button says how
  many are shown ("Columns (5 of 8)").
- **Footer**: lines shown of lines loaded, money out, and the signed total of what's shown.
- **Export**: the lines shown, every column, as CSV, made in the browser.
- **People ↔ lines**: `GET /api/transactions` takes `counterparty_id` and `months` (1 to 36,
  ending at `month`). Each person on People links to "In Transactions (12 months)"; a line's
  person shows as a chip that opens the same.
- Splits stay inline: parts are listed under the line they split, and the editor opens on the
  row.

## Consequences

- No schema change. Filters other than month, period, person and counterparty run in the
  browser on the loaded lines (at most 2,000 for a 12-month period).
- `matches()` remains for saved views of 0.42 and its tests; `keep()` is the full filter.
