# ADR-028: Spending one level deeper: blocks, merchants, products and ways to save

Status: accepted (0.44.0, Nov 2026)

## Context

The redesign's fourth PR (ADR-025). Spending answered "how much per category", but not "where
exactly", "at what price" or "what could change". Invoices (ADR-021) already carry products and
prices; statements carry merchants; nothing put them side by side.

## Decision

- **Spending views** (`view` in the URL): **Groups** (default) shows the month as a
  **treemap**, block size = amount, each block a button that opens the group's merchants with a
  drill path; the category table with last month and last year stays below. **Merchants** lists
  visits, spent, average ticket and how many invoices back them. **Products** lists the
  month's invoice products. **Fixed vs variable** keeps the person, country and fixed
  breakdowns.
- KPI tiles: spent (vs last month, lines), fixed, variable, and **not yet explained** (lines
  without a category).
- **`GET /api/spending/merchants`** (month, person, group, category): statement lines from
  `mart.v_spending_line` grouped by merchant key (as the Inbox groups them); a visit is a
  charge, refunds reduce the amount; invoices counted by the lines they paid.
- **`GET /api/spending/products`** (month, product group, store): invoice lines by product key
  with times, quantity, spent, the unit price paid (tax included), the unit price over the three
  months before, and another store that sold it at least 5% cheaper in the last six months,
  with what the month would have cost there.
- **`GET /api/spending/ideas`** (month, person): patterns read from the month's own lines,
  biggest first: fees and interest, delivery apps (Rappi, Tipti, Uber Eats, PedidosYa, Glovo,
  DiDi Food), small frequent charges (5+ visits averaging $15 or less), merchants new this
  month ($50+, not seen in six months), groups $100 and 25% above their three-month average,
  and products cheaper elsewhere. The amount is what the pattern cost in the month, never a
  promised saving. Each idea links into the view that shows it.
- Purchases links to the Products view to compare unit prices and stores.

## Consequences

- No schema change; thresholds are constants in `services/shopping.py`.
- A store is the invoice's issuer name, so two branches of one chain under one issuer count as
  one store.
- Workbook months have no merchants or products; their views say so.
