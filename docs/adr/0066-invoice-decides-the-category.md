# ADR-066: The invoice decides the category

Status: accepted (0.78.0, Nov 2026)

## Context

A merchant name says little about what was bought: Supermaxi sells food, medicine and cleaning
products, and Fybeca groceries as well as medicine. The plan (Nov 2026, Phase 3) asked that a
matched invoice's products choose the category. Invoices were also matched to their paying line
only when Purchases was opened.

## Decision

- `services/invoice_category.py`: a product's category is the one a person chose for it
  (ADR-050), else its aisle's (food, household and personal care → Groceries / Supermarket; Baby
  → Childcare / Baby & Kids Stores; Health & Pharmacy → Health / Pharmacy; Pets → Pets / Pet Food
  & Supplies; Car → Transport / Fuel). When one category holds at least 60% of the invoice, the
  paying line gets it, with `category_source = 'invoice'` (migration 0045) and a change-log row.
- A category a person chose (manual), a person's or note's, a split, a matched transfer or a
  transfer line is never changed.
- Invoices are matched, and their categories applied, when an invoice is stored, when a
  statement is approved, after a bank sync, and when Purchases opens.

## Consequences

A mixed receipt (no category at 60%) keeps the merchant's category; splitting a line by its
invoice is left for later.
