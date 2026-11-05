# ADR-025: Ledger look and a grouped sidebar

Status: accepted (0.41.0, Nov 2026)

## Context

Hernan and Lauren found the app hard to move around: fifteen links in one top bar, a plain look,
pages that read as lists. A redesign was proposed on a canvas ("Household Cashflow redesign":
navigation, look, nine page mockups, a plan in nine PRs) and approved on Nov 5, 2026. This ADR
covers the first PR: the shell and the look. The pages themselves change in the next PRs.

## Decision

- **Sidebar instead of a top bar**, pages in five groups: Home; Analyze (Spending, Purchases, Net
  worth); Daily (Inbox, Transactions, People & transfers); Plan (Bills, Subscriptions,
  Forecast); Reports (Monthly report, Data health, Import). Upload statements, Settings, the
  signed-in person and the database status at the bottom. On screens under 1024 px a menu
  button opens it above the page. A skip link jumps to the content.
- **Names follow what the page is for**: Review → Inbox (with the count of lines waiting),
  Recurring → Bills, Projections → Forecast, Debt & Net Worth → Net worth, Data Status → Data
  health, Report → Monthly report, Overview → Home. URLs don't change, so links and bookmarks
  keep working.
- **Ledger tokens** (docs/design-system.md): Space Grotesk and Inter, a grey canvas with white
  cards, a navy sidebar, new primary, status and chart colors; dark mode re-tuned. Every text
  pair passes AA.
- **KPI tiles** as a shared component, first on Home.

## Consequences

- Pages keep their current content inside the new shell until their own PRs (Home and Cash flow,
  Spending, Inbox, Transactions, Bills, Net worth, Forecast and Report).
- Personalization (per-person settings, columns, saved views) and the person switch come in the
  next PR, so the top-bar controls from the mockups aren't here yet.
