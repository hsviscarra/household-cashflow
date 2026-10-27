# ADR-012: Balance sheet from statements, holdings and snapshots

- Status: accepted
- Date: 2026-10-27

## Context

The Debt & Net Worth page (F14, issue #16) showed what interest and fees cost but not what the
household owns and owes. Hernan asked for a balance sheet with plots and cards: the workbook's
debts (the BIESS loan, cards, what is left to pay two lenders), the properties and car, bank
balances, investments, credit card debt, and a house being bought with a 30% down payment paid
in installments before delivery. The workbook's debts and savings were already loaded as
`core.balance_snapshot` rows (F2) but nothing showed them.

## Decision

- **Three sources of value.**
  - *Bank accounts and cards:* each one's latest approved statement closing balance on or before
    the date. Checking and savings are cash; a card is a liability.
  - *Holdings* (`core.holding`, migration 0015): anything else owned or owed, as property,
    vehicle, investment, cash, purchase, loan, money owed to a person, card or other. A holding's
    value is its latest balance snapshot on or before the date, from the workbook, entered on the
    page, or (next) read from a loan's payment history PDF. Snapshots now carry `holding_id`.
  - *A purchase in progress:* the asset is what has been paid so far (the latest "paid so far"
    plus later lines in its category). The rest of the down payment, and the part financed at
    delivery, are **commitments**: shown, not counted, because neither the house nor its loan
    exist until delivery.
- **Migration 0015** creates the holdings for the workbook's snapshots: BIESS is a loan,
  "Remaining to pay" lines are money owed to people, other workbook liabilities are cards,
  Stock Market is an investment, and the rest is cash. A workbook reload links its new snapshots
  to the same holdings. The downgrade drops the page's values: they have no place before 0015.
- **Values are dated.** Entering a value for a date creates a snapshot; the same date again
  replaces it. The page asks for the date the item was bought (or the loan taken) so past months
  include it. Net worth over time is computed for the last 24 month-ends from what was known on
  each.
- **A loan can point to its recurring payment** (F11): the card shows the monthly payment and
  the payments made this year.
- **Real values never enter git.** The properties, car and new house are entered on the page.
  The BIESS balance updates from the payment history PDF once its parser exists; until then it
  is the workbook's balance.

## Consequences

- Net worth, total owned, total owed and commitments are on one page with a chart and table.
- Workbook card balances that statements now cover (an old Mastercard entry) can be paused
  from counting or removed.
- Snapshot values are as entered; nothing depreciates or amortizes by itself.
