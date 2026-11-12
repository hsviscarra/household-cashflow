# ADR-090: Net worth in two pages: Overview and Manage

Status: accepted (0.99.0, Nov 2026). First item of phase 3 in the improvement plan.

The Net worth page did two jobs at once. To read where the household stands, one scrolled past a
card per item with its buttons, forms, loan tables and history; to update a value, one scrolled
past totals and charts. ADR-032 added a "show only what's out of date" switch, which helped
neither reading nor editing much.

## Decision

- **Overview** (`/debt`, the sidebar's Net worth): the headline, the five tiles, what you own and
  what you owe as one line per item (name, value, the value's date, "out of date" when it is),
  grouped by kind with subtotals, then the trend, investments and interest and fees. No forms.
  When values are out of date, one button goes to Manage with only those shown.
- **Manage** (`/debt/manage`, a tab): the cards with their actions (update value, edit, history,
  payments, loan table, pause), Add something you own or owe, and the paused items.
- One component, `BalanceSheetSection`, with `mode`; the item cards and forms are unchanged.
- To do's out-of-date values link to Manage (they pointed to an address that didn't exist).

## Consequences

- Reading and editing no longer share a screen; nothing was removed.
- Both pages read the same `/api/networth` answer, cached once by the browser.
