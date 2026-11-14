# ADR-106: The web app split by section; the API client by area

Status: accepted (0.115.0, Nov 2026). No change in what any page shows.

## Context

ADR-102 set a limit of 400 lines a web source file and listed the 23 files over it as a baseline:
`api.ts` (2,138 lines), Settings (1,459), Recurring (1,216), Transactions (1,141), Net worth
(1,095), Home (960) and 17 more between 417 and 754.

## Decision

- **A page that holds several sections is a folder.** The page file keeps the page and its state;
  each section, form or card is a module beside it, with what they share in `shared.tsx`:
  `pages/settings/` (accounts, categories, rules, bank sync), `pages/recurring/`,
  `pages/transactions/` (cells, editor, columns, filters, phone list), `pages/networth/`,
  `pages/home/` (the cards, by kind), `pages/projections/`, `pages/todo/`, `pages/bills/`,
  `pages/cashflow/`, `pages/groceries/`, `pages/import/`, `pages/purchases/`,
  `pages/spending/`, `pages/overview/`, `pages/people/`, `pages/status/`, `pages/taxes/`.
  Components the same way: `components/chart/`, `components/table/`, `components/merchant/`,
  `CreatePanel`, `categoryPick`, and the app's `Sidebar`.
- **The API client is one module per area** under `src/endpoints/` (settings, history, imports,
  recurring, analysis, forecast, invoices, months, plans, saving, and `http` for the fetch
  helpers). `src/api.ts` re-exports exactly what it exported before, so no import changed.
- Page files re-export the helpers their tests import, so tests didn't move.
- The moves were made with a script that moves whole top-level declarations and rewrites the
  imports on both sides, refusing any move that would make the new module depend on the old
  one; nothing was retyped by hand except the Transactions page, whose component alone was over
  the limit (its columns, filter bar and phone list are now their own modules).

## Consequences

- The exemption list in `web/eslint.config.js` is gone: every source file is under 400 lines.
- A new section of a page is a new module in its folder; a new endpoint goes in its area's module
  and one line in `src/api.ts`.
