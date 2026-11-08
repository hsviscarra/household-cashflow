# ADR-053: Confirm loan payments from To do, no new tables

Status: accepted (0.67.0, Nov 2026)

## Context

Hernan: "For BIESS I don't want to upload amortization tables. I just want at the end of the month
to be asked if I paid, and based on the amortization table I have, update the numbers." A loan's
balance only moved when a newer table was uploaded.

## Decision

- `POST /api/holdings/{id}/installments/{number}/paid` marks that installment and every earlier
  one paid and adds the table's balance after each as the loan's value (dated the 1st of its month,
  like an imported table).
- To do gains **Loan payments to confirm**: for each active loan with a table, the next
  installment still to come, from the 25th of its month, or any day once its month has passed.
  The task shows principal, interest and the balance after; **Yes, paid** confirms it.
- The table is still uploaded once (and again only if the lender changes it).
