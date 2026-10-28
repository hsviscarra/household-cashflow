# ADR-013: Projections from recurring items, cash-terms variable spending and installments

- Status: accepted
- Date: 2026-10-27

## Context

F15 (issue #17) adds a 3-month projection, the lowest balance between paydays and alerts for
categories more than 30% above normal. It is done when the next 3 months' projection is on
screen. The pieces exist: recurring items (F11), the spending view (F13), statement balances and
purchases in progress (F14).

## Decision

- **Cash terms throughout.** The projection answers "how much will be in the bank":
  - *Income and fixed outflows:* the recurring items, including card payments. Each month uses
    its entry when generated (a skip counts nothing, a one-month change counts as changed),
    else the template's amount. Entries already paid by a line are left out.
  - *Variable spending:* the average of the last three complete months of spending lines that no
    recurring item paid and that are not card purchases (the card payments carry those), from
    `mart.v_spending_line`.
  - *Purchase installments:* each active purchase in progress (F14) adds its installment while
    installments are left, unless a recurring item already pays its category (counted once).
  - *Starting cash:* the bank accounts' latest statement closing balances (the oldest date is
    shown).
- **Cash timing.** Day by day from today to the end of the third month:
  - each recurring item lands on the day of the month it was last paid by a statement or manual
    line (the 1st when it never was);
  - installments land on the day of their last payment;
  - variable spending is spread evenly over each month's days.
  The lowest point and the next income after it ("before the salary on the 21st") lead the page,
  with a warning when cash goes below zero.
- **Alerts:** in the last complete month, spending groups more than 30% and at least 25.00
  above their average of the three months before. The average counts the months that have any
  spending. A group new this month has no average and raises no alert, because coverage changes
  (a newly loaded card) would otherwise flag every category.
- **Computed in Python** (`services/projections.py`, `GET /api/projections`), not as
  `mart.v_projection`: it combines templates, holdings and day-level timing. No schema change.

## Consequences

- The projection is as good as the recurring items: an item never generated still counts at
  its template amount, and an income item without a statement line lands on the 1st.
- Starting cash is only the accounts with statements; cash elsewhere is not included until its
  statements are loaded.
