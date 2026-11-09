# ADR-055: Money between the US and Ecuador through people

Status: accepted (0.69.0, Nov 2026)

## Context

Hernan: "We did not transfer money from the US to Ecuador. We paid people in the US who have
accounts in both countries, and they transferred us the same amount in Ecuador." A Zelle payment
from Bank of America to such a person was spending (Other Expenses) and their deposit in
Produbanco or Pichincha was income, so both money in and money out were inflated, and "kept" and
the down payment didn't add up. Transfer matching only paired lines without a person, at most
5 days apart.

## Decision

- Migration 0039 adds **Transfers / Exchange through people** (kind transfer): not income or
  spending.
- A person (People & transfers) whose category is Exchange through people gives their lines that
  category, as any person's category does (ADR-023); Always on a Zelle line in To do or the lines
  panel makes it a rule.
- Transfer matching pairs an exchange line with its other side like a move between own accounts:
  opposite amounts on two different accounts, the other side a transfer or without a category,
  and up to **10 days apart when the two accounts are in different countries** (5 within one).
  Both legs keep Exchange through people. Saving a person runs matching.
- Where's the money no longer counts a paired exchange under "money with people".

## Consequences

- Moving money between countries stops counting as income and spending. Exchanges where the
  amounts differ (a fee, or one deposit for several payments) stay transfers without a pair and
  show under "Transfers missing the other side" until matched by hand.
