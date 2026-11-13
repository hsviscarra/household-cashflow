# ADR-095: Compare with a year earlier, give ticked lines to a person, invoices on the shared table

Status: accepted (0.105.0, Nov 2026). Plan items B3 ("compare with"), B2 (bulk actions) and B1
(Purchases). Web only: no new endpoint and no schema change. One release (ADR-092).

## Decision

- **Compare with a year earlier.** The Spending chart's fourth control. The same months a year
  before are asked from the series endpoint (ADR-094) as one whole series and drawn as a line
  over the columns; the table and the CSV get "A year earlier" and "Change". With "This year"
  the comparison is January to the same month of last year. The line isn't drawn in "Share of
  the month", where the columns are percentages.
- **Ticked lines can be given to a person.** Next to "Categorize as" on Transactions: "Whose"
  (Hernan, Lauren, Joint). It sends the existing one-line change for each ticked line, so every
  change is in the line's history like any other.
- **"Mark as transfer" is "Categorize as" a transfer category.** A line's type follows its
  category (`classify.set_category`), so the bulk action that exists already does it; pairing
  the two sides stays on To do → Transfers, which knows both sides. No second way to do it.
- **Purchases' invoices on `DataTable`.** Sort, choose columns (date, payment, in whose name,
  number, products, before tax, VAT), group by supplier, payment or person with subtotals, and
  "Find in this table" looks in the products too, so an invoice is found by something bought.
  The products and "Split the bank line by category" open under the row.

## Not in this release

- A bulk endpoint: at most a few dozen ticked lines, one small request each, and each keeps its
  own history entry. Logged in `docs/refactors.md` to revisit if it is ever slow.
- The same chart controls on Home, Net worth and Groceries: each needs its own series endpoint.
