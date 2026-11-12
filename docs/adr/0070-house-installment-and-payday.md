# ADR-070: The house installment by amount, and early salaries in their month

Status: accepted (0.80.0, Nov 2026); the early-salary rule is replaced by ADR-084 (0.93.0)

## Context

Two things left holes in the July–October cash flow:

- The new house's installments (3,075.36) and the 25,678.22 down payment leave Lauren's
  Produbanco as "TRANSFERENCIA CTAS TERCEROS BCA ENL". That text never names the developer's
  trust, so the KALANI rule (ADR-056) missed them and they stayed transfers between own accounts,
  which the cash flow leaves out.
- Lauren's payroll ("ROL DE PAGOS") sometimes lands on the 1st: September had no salary from her
  and October had two.

## Decision

- A rule for "TRANSFERENCIA CTAS TERCEROS" at exactly 3,075.36 sends the installment to Housing /
  New house, at priority 5 so it wins over any rule about those transfers. Migration 0046 adds it
  and moves the installments and the down payment already loaded (not those a person
  categorized), clearing a one-sided transfer mark.
- `payday.cash_month`: a positive "ROL DE PAGOS" line dated the 1st or 2nd counts in the month
  before. The loaders (statements and bank sync) use it, and migration 0046 moves the salaries
  already loaded.
- Every change is in audit.change_log; the downgrade puts the logged values back.

## Consequences

Each month shows one salary from Lauren and the house payments as debt payments. A different
installment amount (a final one, a change) needs the rule's amount edited in Settings → Rules.
