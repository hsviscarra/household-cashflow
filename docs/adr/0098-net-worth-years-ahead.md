# ADR-098: Net worth five to ten years ahead

Status: accepted (0.108.0, Nov 2026). Plan item C4. No schema change. Arithmetic on stated
assumptions, in today's money; not a prediction and not a recommendation.

## Decision

A tab of Net worth, "Years ahead" (`/debt/ahead`), with net worth at the end of this year and of
each of the next 5 or 10.

- **What a year adds.** What was kept (money in less spent, ADR-073) in the last complete
  months, as a yearly pace. It pays the loans first; the rest stays as cash or is invested, by
  a share the person chooses (0 by default: the app doesn't assume you invest).
- **Loans.** A loan with an amortization table follows it: its balance at each year's end, and
  the year's interest, which is taken from what is kept (loan payments are "set aside" in the
  measures, so their interest isn't in "spent"). A loan without a table goes down by its
  monthly payment and no interest is counted; the page names those loans.
- **Investments** grow at a yearly return: low, expected and high (2%, 5%, 8% until changed),
  which is where the range of net worth comes from.
- **Property and vehicles** change by a yearly rate each (0% and −10% until changed). Cards and
  other debts stay as they are: the monthly forecast is where they live. Purchases in progress
  stay at what was paid: their installments move cash into them, which leaves net worth alone.
- **Milestones.** Each loan's last installment and each open goal's date are placed in their
  year; the person adds their own (a school stage), kept in their settings.
- **Layers.** `services/long_view.py` is pure (Decimal, tested with hand-worked years);
  `services/outlook.py` reads the balance sheet, tables, measures and goals and calls it.

## Assumptions (constants in `long_view.py`, all choices on the page)

Returns 2% / 5% / 8%; property 0%; vehicles −10%; share invested 0; 5 or 10 years. The rest of
the running year counts its whole months left.

## What it leaves out

Income that grows, inflation (everything is in today's money), taxes on returns, a new loan at
the house's delivery (the commitment is shown on Net worth, not projected here), and spending
that changes with the milestones. Each would be a choice on the page; none is assumed silently.
