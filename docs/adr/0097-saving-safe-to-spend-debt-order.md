# ADR-097: Saving on one page, safe to spend, and the order to pay debts in

Status: accepted (0.107.0, Nov 2026). Plan items C5 and C6. No schema change. Calculations from
the household's own numbers; nothing here recommends an investment or a product.

## Decision

### The page (C5) — `/savings`, a tab of Budget & goals

- **Savings rate by month.** Kept (money in less spent, ADR-073) over money in, for the last 12
  months; the rate of the period leaves the running month out.
- **What the goals need.** Each open goal's amount a month to arrive on its date (ADR-040), what
  is planned, and what went into savings this month so far (lines of type `savings`).
- **Debts and the order to pay them in** — `services/payoff.py`, pure and in Decimal. Each month
  a debt grows by a twelfth of its yearly rate and gets its payment; the extra and the payments
  of debts already paid off go to one debt at a time: highest rate first, or smallest balance
  first. "Minimums only" rolls nothing over. The page shows months to debt-free, interest paid
  and the order, and says which order costs less and by how much. Tested against the loan
  formula.
- **Where a debt's terms come from.** Typed on the page wins (kept per debt in an app setting,
  `debt-terms:<item>`; no new table). Otherwise: a loan with an amortization table gives its
  next installment and a yearly rate estimated from the interest left in the table; a card's
  rate is estimated from this year's interest against its balance, and its payment is assumed
  at 3% of the balance (25.00 at least). Every number says where it is from. A debt without a
  rate or a payment is listed but not compared. A card that charged no interest has no rate:
  paid in full, it costs nothing.

### Safe to spend (C6) — a Home widget and the top of the page

`safe = (money in − spent − set aside, so far) + income still to come − bills still due −
what the goals' plan still needs this month`, and the same per day left. "Still to come" and
"still due" are the forecast's own events for the rest of the month (`projections.rest_of_month`):
recurring items, loan and purchase installments, income tax. A salary that arrives this month
for the next one isn't counted (ADR-084). It is always the month running now.

A widget added to Home after a person saved their list shows up once for them (the saved list
now records which widgets it knew), so nobody has to find it under Customize.

### Subscriptions

An active subscription whose last charge is over its earlier ones by 3% and at least 0.50 says
"Went up" with the amount.

## Corrected after the first look at real data (0.110.0, Nov 13 2026)

A card's statement balance is this month's purchases unless it is carried, and the app can't
tell which. The first version estimated a rate from the year's interest (0.3% to 4%) and
assumed a 3% payment, which made five cards look like debts that take three years to pay. Now a
card has no rate and no payment, and isn't compared, until its rate is typed; with a rate
typed, its payment is assumed at 3% of the balance (25.00 at least) until that is typed too.
What a card cost in interest and fees over twelve months is still shown.

## Assumptions (constants in `services/savings.py`, `payoff.py`, `subscriptions.py`)

`RATE_MONTHS` 12; `CARD_MINIMUM_SHARE` 3%, `CARD_MINIMUM_FLOOR` 25; `MAX_RATE` 200%;
`MAX_MONTHS` 600; `PRICE_UP_SHARE` 3%, `PRICE_UP_MIN` 0.50.

## Not in this release

- Budget amounts suggested from history: the Budget page already starts from the average
  (ADR-039); nothing new was needed.
- The same subscription on two cards: charges of one merchant are grouped whatever card they
  are on, so two cards read as one uneven subscription. Finding it needs the grouping split by
  card first; logged in `docs/refactors.md`.
- Whether a month "covered" each goal one by one: savings lines aren't tied to a goal.
