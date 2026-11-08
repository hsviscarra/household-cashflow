# ADR-050: Purchases use the app's categories

Status: accepted (0.64.0, Nov 2026)

## Context

Purchases had its own fixed list of grocery groups (Dairy & Eggs, Pantry, …). School fees
("aporte pensión educación inicial") or school transport had nowhere to go, and the list was a
third set of categories next to the app's and SRI's. Hernan asked whether choosing would work like
a rule next time, and how purchases relate to the cash flow.

## Decision

- Migration 0037: `core.invoice_line.category_id` and `core.product_rule.category_id`;
  `product_rule.product_group` becomes optional.
- `PUT /api/invoices/products` takes `category_id` (or, as before, `product_group`). A category is
  kept as the product's rule and set on every line with that product, now and on later invoices:
  choosing works like a rule. Lines with a category leave the list to categorize.
- Purchases shows "N products need a category" with the shared category picker (which can add a
  category, e.g. Education → School fees); the old group is shown as a hint ("looks like Dairy &
  Eggs"). Each invoice's table shows the item's category.
- **Relation to the cash flow:** when an invoice is matched to the bank or card line that paid it
  and its items fall in two or more categories, "Split the bank line by category" splits that line
  (the existing split) into one part per category, with the invoice total winning over
  rounding. The cash flow then counts each category.
- Grocery groups stay for the grocery insights (prices, cheaper stores); they're no longer what a
  person is asked to choose.
