# ADR-036: Gastos personales from the SRI invoices

Status: accepted (0.52.0, Nov 2026)

## Context

Phase 1 of the improvement plan (Nov 6, 2026). Each person in Ecuador may deduct personal
expenses invoiced to their cédula, in six SRI categories, up to a cap of 7 basic baskets
(more with cargas familiares), and gets 18% of it off their income tax. In 2026 the basket is
USD 821.80, so the cap with no cargas is USD 5,752.60 and the rebate up to USD 1,035.47. The app
already keeps every invoice XML (ADR-021) but not whose it is or its SRI category.

## Decision

- **Whose invoice.** While an XML is read, the buyer's ID is compared with `INVOICE_BUYERS`
  ("Hernan:<cédula>,Lauren:<cédula>", a Container App secret set by `setup-buyers.sh`); a RUC
  ending in 001 matches its cédula. Only the name goes to `core.invoice.person`; the ID is never
  stored. Without it: the person of the card or bank line that paid the invoice, or a person's
  choice.
- **SRI category**, in order: a person's choice on the invoice (`gp_category`, or `none` = not
  deductible); the issuer's rule (`core.gp_issuer_rule`, by RUC, saved with "All from this
  issuer"); the category of the line that paid it (a fixed map: Supermarket and restaurants →
  Alimentación, health and pharmacy → Salud, daycare and courses → Educación, clothing →
  Vestimenta, lodging → Turismo, property tax → Vivienda); the products (half or more of the value
  food, or pharmacy); else none yet. Utilities, condo fees and mortgage payments aren't guessed.
- **Cap and rebate.** `core.gp_profile` keeps cargas and the catastrophic-illness case per person
  and year. Cap = basket × 7, 9, 11, 14, 17 or 20 baskets (100 for catastrophic). Deductible =
  the lesser of the total and the cap; rebate = 18%. Baskets per year live in code (`CANASTA`).
- **Amounts** are the invoice's value before IVA (base imponible), the conservative reading;
  the page shows the total paid too.
- **API**: `GET /api/gastos/{year}`, `GET /api/gastos/{year}/invoices` (`status=to_classify`,
  `person=none`), `PUT /api/invoices/{id}/gastos`, `PUT /api/gastos/{year}/profile/{person}`,
  `GET /api/gastos/{year}/{person}.csv` (per issuer and category, for the annex).
- **Page**: Gastos personales under Plan: per person the rebate, the cap bar, the six categories,
  cargas; then the invoices to sort out, with whose and which category set in place.
- Migration 0031 (columns on `core.invoice`, two tables), with a downgrade.

## Consequences

- Invoices issued to "consumidor final" or to someone else stay unassigned until a person chooses.
- Expenses with no electronic invoice (BIESS mortgage interest, school fees paid abroad) aren't
  counted; they can be added later as manual entries.
- The deadlines for the projection form and the annex follow the SRI calendar; the app doesn't
  file anything.
