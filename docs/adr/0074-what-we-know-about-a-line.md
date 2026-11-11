# ADR-074: What we know about a line, and Juliana's card

Status: accepted (0.83.0, Nov 2026)

## Context

Hernan could edit a line on Transactions but not see what he needed to decide what it was, nor
open its statement. Lauren's Diners card is kept for Juliana's education (Colegio Einstein's
tuition, bus and insurance; Skole's food), but it may sometimes pay for something else, and he
wants those flagged to check by hand.

## Decision

- `line_context.build` and `GET /api/transactions/{id}/context`: lines of exactly the same amount
  with their categories ("Use this category"), the transfer's other side or its candidates (same
  amount, opposite sign, another account, within 7 days), the invoice the line paid or invoices of
  its amount within 5 days ("This is the one": `PUT /api/transactions/{id}/invoice`, after which
  the invoice's products may set the category, ADR-066), the rule that sets lines like it, and
  the card's purpose.
- The open line on Transactions shows it under "What we know", with "Open the statement" (the
  PDF) and "Show where it is on the statement" (the text around the line).
- A card kept for one purpose is `core.app_setting` `card-purpose:<account_id>` =
  `{"for": "Juliana", "usual": ["EINSTEIN", "SKOLE", "DEUDA ASEGURADA"]}` (migration 0049, no
  schema change). Its lines whose description has none of those words, and aren't fees, interest
  or payments to the card, appear on To do under "Check: unusual on Juliana's card" for 120 days:
  "It's Juliana's" (not asked again) or choose its category.

## Consequences

A new usual merchant on the card is flagged once per line until it is added to the list (for now
by migration or by Claude; a Settings field can come later).
