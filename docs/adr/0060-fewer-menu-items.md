# ADR-060: Fewer menu items, pages as tabs

Status: accepted (0.72.1, Nov 2026)

## Context

Hernan (Nov 9 2026): "I don't want to keep adding more" to the sidebar; Groceries had just made it
16 links.

## Decision

Pages that answer one question become tabs of one sidebar item (`FAMILIES` in App.tsx):

- **Spending**: Categories (/spending) · Groceries (/groceries) · Purchases (invoices) (/purchases).
- **Budget & goals**: Budget (/budget) · Goals (/goals).
- **Taxes**: Deductions (/taxes); Monthly IVA joins it later.

The sidebar item stays current on any of its tabs; the tabs sit above the page as an underlined
row. Import leaves the list (Upload statements at the bottom opens it). Every address still works.
Sidebar: Home, To do · Cash flow, Spending, Bills & subscriptions, Transactions, People & transfers
· Net worth · Budget & goals, Forecast · Taxes, Monthly report.

## Consequences

A new page joins a family as a tab unless it answers a new question.
