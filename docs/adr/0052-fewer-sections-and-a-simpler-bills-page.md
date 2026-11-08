# ADR-052: Sidebar by what it answers, and a simpler Bills page

Status: accepted (0.66.0, Nov 2026)

## Context

Hernan: "Instead of interactivity the tendency is to create more and more tabs... the bills and
subscriptions page is horrible, not well designed, and I don't know why it is with forecast,
budget, goals and tax deductions."

## Decision

- Sidebar groups by the question they answer:
  - **Home**: Home, To do.
  - **Money** (what happened): Cash flow, Spending, Bills & subscriptions, Purchases, Transactions,
    People & transfers.
  - **Wealth** (what you have): Net worth.
  - **Plan** (what's ahead): Budget, Goals, Forecast.
  - **Taxes & reports**: Tax deductions, Monthly report, Import.
- Bills & subscriptions opens on **This month**: one list by what needs attention first (Late,
  Still to pay, Paid, Skipped), each row with its day, category, account, how often, a status pill,
  the amount (and what was expected when it differs) and any price change inline; money coming in
  listed apart; price changes summarized under the list. Calendar, By group, Edit (year grid) and
  Subscriptions are the other views; the separate Price changes view is gone (it's inline now).
- Pages and addresses don't change; nothing is removed.

## Consequences

- The sidebar reads as three questions instead of five buckets; Bills sits with the money it
  describes. Merging pages further (e.g. Spending into Cash flow) is left for when the lines panel
  covers every number.
