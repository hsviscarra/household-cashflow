# ADR-059: Groceries, from the statements and the supermarket invoices

Status: accepted (0.72.0, Nov 2026)

## Context

Hernan (Nov 9 2026): nowhere in Cash flow or Spending shows how the grocery money is spent with
the Supermaxi invoices, the most important ones. Purchases lists every invoice of a month (school,
insurance, fuel…) and Spending's Products view lists products, but neither puts the Groceries
spending next to what it bought, or says which grocery charges have no invoice. In October 2026
only 3 Corporación Favorita invoices (195.19) had arrived, against several hundred dollars of
Supermaxi and Megamaxi charges.

## Decision

A **Groceries** page (Money → Groceries; also "What it bought, product by product" when Spending
is opened on the Groceries group), for one month, last month by default:

- Spent (mart.v_spending_line, Groceries group: statements or the workbook), the usual month
  (average of the three before), a week, and the share that has its invoice.
- The last six months: spent and invoiced side by side; a month's bars open it.
- **Charges without their invoice:** the month's Groceries lines from statements that no invoice
  is matched to, with how to get the invoice (cédula at the till, or the SRI list on Purchases).
- **By aisle:** the invoices' product groups against their average of the months before; products
  not in an aisle point to Purchases, where Claude suggests one.
- **Stores** and **Top products** (unit price against the three months before, from the Spending
  products logic).

A supermarket invoice is one paid by a Groceries line, from a supermarket chain by name
(Favorita, Supermaxi, Megamaxi, Akí, El Rosado/Mi Comisariato, Tía, Santa María, Coral…), or
mostly food by its products. `GET /api/spending/groceries?month=`. No schema change.

## Consequences

The page is only as good as the invoices that arrive; the missing-invoice list makes the gap
visible and says how to close it.
