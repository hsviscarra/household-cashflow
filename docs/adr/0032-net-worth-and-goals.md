# ADR-032: Net worth as a balance sheet you can trust at a glance

Status: accepted (0.48.0, Nov 2026)

## Context

The redesign's eighth PR (ADR-025). The balance sheet had every number but didn't say which
were old, which workbook values double-counted a bank account, what the debts cost a month or
what paying more would change.

## Decision

- **Two columns** on wide screens: what you own and what you owe side by side, by kind, one
  item per row; "Coming at delivery" under what you owe shows purchases' remaining amount as a
  commitment, not a debt.
- **Freshness** on every item: up to date, or out of date with its age. Bank, card, loan and
  purchase values go out of date after 45 days, investments after 10, property and vehicles
  after a year, other after 180; money held for a person never does (it moves with their
  lines). **Update values (N out of date)** shows only those, to update in one pass.
- **Possible duplicates**: an out-of-date workbook value next to an active non-workbook item of
  the same kind says "Probably the same money as …" with **Pause it** (paused items stop
  counting and stay listed).
- **Tiles**: net worth (as of), own (property, cash and investment shares), owe (the largest
  debt's share), **debt payments a month** (loans' payments plus purchases' installments) and
  **interest left on loans** with the last payoff month.
- **What if** on a loan with an amortization table: paying N more a month shows how much sooner
  it ends and about how much interest it saves. The monthly rate is solved from the schedule
  (balance, interest left, months left), so it needs no rate typed in.
- Owed-to-people is labelled "Held for or owed to people", which is where Holding for Rubén
  lives. Goals (the new house's progress, money held for others) also show on Home.

## Consequences

- No API or schema change: freshness, duplicates and the what-if are computed in the browser
  from `/api/networth`.
- The what-if is an estimate on level payments; insurance and charges in the schedule aren't
  part of it.
