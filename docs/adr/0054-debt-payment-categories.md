# ADR-054: Debt payment categories

Status: accepted (0.68.0, Nov 2026)

## Context

Hernan: "House payments are debt payments": the new house ($3,075.36 a month, a purchase being
paid off), the BIESS mortgage on the house bought years ago, and Lauren's US education loans (in
the original workbook). Only workbook months had debt payments: a line loaded from a statement
took its type from the category's kind, and no kind meant debt. Loan Payments sat in Savings &
Debt (kind savings) and Mortgage BIESS in Housing (spending), so these payments showed as savings
or spending and Debt payments looked empty.

## Decision

- A fifth category kind, **debt**: lines in it are debt payments (`debt_payment`), money back on
  it is too (the type follows the kind). Rules, the To do and lines-panel recategorizing, bank sync
  and statements all go through the same type mapping.
- Migration 0038 marks as debt: Savings & Debt / Loan Payments, Housing / Mortgage BIESS, and every
  category a loan or a purchase in progress (the new house) is paid through; their savings or
  spending lines and recurring items become debt payments. Downgrade returns them to savings
  (Mortgage BIESS to spending), keeping the workbook's own debt payments.
- Settings and the category picker offer "Debt payments" as a kind, so a new loan (a car) can be
  one.

## Consequences

- Cash flow's Debt payments, the Where's the money check and the budget see loan and house
  payments as what they are; Savings shows only money put aside or invested.
