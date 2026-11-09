# ADR-061: Grocery products by aisle, type and brand

Status: accepted (0.73.0, Nov 2026)

## Context

Hernan (Nov 9 2026): the Groceries page doesn't show the full detail; "all the items that I buy I
need to classify them so I know what I'm spending the most on: types of food, brands". Products
only had an aisle (product group), and most had none.

## Decision

- Migration 0042 adds `product_type` and `brand` to core.invoice_line and core.product_rule, and
  `label_source` (claude | confirmed) to invoice_line.
- **Claude labels** the supermarket products of the period shown that have no labels yet (up to
  120 a call): aisle (only where none is set), type as a short general English noun (Cheese,
  Chicken, Diapers) and brand as printed, or none. It runs on its own when Groceries → Products
  opens. Only descriptions are sent, as for product groups (ADR-021).
- **A person corrects** aisle, type or brand on a product's row; it becomes the product's rule
  (with Claude's other labels) and applies to every purchase of it now and on later invoices.
- **Groceries → Products** (Overview | Products switch, `?view=products`): this month, 3 or 12
  months; "Where it goes" totals by aisle, type or brand (a bar opens its products); every
  product with aisle · type · brand, times, quantity, unit price and spending; search.
- API: `GET /api/spending/groceries/products?start=&months=`, `POST /api/spending/groceries/label`,
  `PUT /api/spending/groceries/products`.

## Consequences

Types and brands are only as complete as the invoices that arrive. Claude's labels are marked
until a person saves the product.
