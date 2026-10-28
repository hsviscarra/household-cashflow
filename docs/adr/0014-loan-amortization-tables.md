# ADR-014: Loan balances and installments from the lender's amortization table

- Status: accepted
- Date: 2026-10-27

## Context

The mortgage's balance on the balance sheet (F14, ADR-012) came from the workbook or from a value
typed on the page. The lender (BIESS) publishes an amortization table as a PDF. For every
installment it lists the number, the month, principal, interest, insurance and other charges, the
total, the balance after it, and whether it is paid (CANCELADO) or still to come (POR VENCER).
Hernan downloads it and pays each installment by bank transfer. Those transfers appear in the bank
statements.

## Decision

- **Upload the table on the loan's card.** `POST /api/holdings/{id}/schedule` reads the PDF into
  `core.loan_installment` (migration 0016), one row per installment. Each row has number, month,
  principal, interest, other, total, balance after and status (paid or due). A newer table
  replaces the older one.
- **Read rows from text, check before saving.** Each row is read as `N YYYY-MM amounts… TOTAL
  BALANCE STATE`:
  - the first two amounts are principal and interest;
  - the last two are the total and the balance;
  - whatever is between is "other". Blank columns are simply missing, so no column positions are
    needed.

  Nothing is saved unless all of these hold to the cent:
  - installments run 1..N with no gaps;
  - each row's amounts add up to its total;
  - each balance equals the previous balance less the principal (the first from the approved
    amount).
- **Numbers only.** The ID number, name and loan number in the header are not read or stored,
  and neither is the file. `audit.load_log` keeps the file's hash.
- **The balance comes from the table.** One `balance_snapshot` (source `amortization`) per paid
  installment holds the balance after it. It is dated the first of its month, because the lender
  already counts it paid. Values typed on the page and the workbook's balances stay as earlier
  history.
- **Summary on the card:** installments paid, the next installment and its month, the payoff
  month, interest paid this year, and the interest and other charges still to pay. The loan's
  monthly payment becomes the next installment.
- **Payment check.** The last 12 installments and the next 3 are each matched to the bank line
  that paid it, using a statement or manual outflow that meets all of these:
  - within 1.00 of the installment;
  - from the 15th of the month before to the 15th of the month after;
  - and at least one of: linked to the loan's recurring item, in its category, or with
    IESS/BIESS in the description.

  Each line pays one installment. A paid installment with no line shows "no bank line found".
  That usually means the statement that carries it hasn't been loaded yet.
- **Projections use the table.** A recurring item linked to a loan with a table projects that
  month's installment, and nothing after the payoff month.

## Consequences

- The balance sheet's mortgage balance is exact to the lender's numbers and moves each time a
  newer table is uploaded. Typing a value is still possible, and the latest value wins.
- Other lenders' tables work when they follow the same row shape. A table that doesn't check out
  is refused with the first problems found.
- The payment check relies on bank statements. Months that only the workbook covers (ADR-004)
  have no lines to match.
