# ADR-007: Transfers are matched across accounts; spending view and cash view

- Status: accepted
- Date: 2026-10-26

## Context

A card payment or a move between own accounts appears on two statements: money out of the bank
account and a payment received on the card (or money into savings). Counted on both sides it
doubles the outflow; dropped on both sides, the bank account's real cash leaving the household
disappears. F10 (issue #12) asks for transfer matching and two ways to read a month: card
payments are left out of spending and shown in the cash view.

## Decision

- **Matching links the two legs.** `core.transaction.transfer_group_id` holds the smaller
  transaction id of the pair (migration 0011, with an index). Two statement lines are paired when
  their amounts are opposite and equal, they are on two different accounts, at most 5 days apart,
  at least one is already a transfer and the other is a transfer or still has no category. The
  closest date wins, then the oldest line. Both legs become `type = transfer`, `status = matched`
  and get *Transfers / Card Payment* when one side is a credit card, otherwise *Transfers /
  Between Own Accounts*, with `category_source = 'match'`. Every change is written to
  `audit.change_log` ("Matched transfer").
- **A category Hernan chose is never overridden.** Lines categorized as something other than a
  transfer, split lines and parts of a split are left alone. Re-categorizing a matched leg to a
  non-transfer category unlinks the pair; the Transactions page also has "Not the same money:
  unlink".
- **When it runs:** after an import is approved, after the Review page resolves a merchant to a
  transfer category, after a line is edited into an unmatched transfer, and on "Match transfers
  again" (`POST /api/transfers/match`). Transfers whose other side isn't loaded are listed on the
  Review page (`GET /api/transfers/unmatched`): usually the other account's statement is missing.
- **Two views of a month.**
  - *Spending view* (`mart.v_monthly_cashflow`, unchanged): every account, card purchases counted
    when they happen; transfers, card payments included, are left out.
  - *Cash view* (`mart.v_monthly_cash`, new): only bank accounts (checking and savings) plus the
    Excel history (ADR-004 still applies). Card purchases are not counted; the payment from the
    bank to a card is, as `card_payments`. Moves between own bank accounts are left out. A
    transfer counts as a card payment when its category is *Card Payment* or its matched other leg
    is on a credit card account.
  - `GET /api/cashflow/monthly?view=spending|cash`; the Overview has a Spending view / Cash view
    toggle (`?view=cash`).

## Consequences

- Real statements pair as expected (Produbanco → Pacificard payments, BofA checking → savings).
  A card payment whose paying account isn't loaded still counts in the cash view by its category,
  and is listed as unmatched until that statement is uploaded.
- A matched pair can be wrong (two unrelated lines of the same amount within 5 days); unlinking
  is one click and is logged.
- The cash view for months covered by the Excel history shows the history's numbers, which have
  no card payments of their own.
