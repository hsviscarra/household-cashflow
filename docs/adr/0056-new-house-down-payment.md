# ADR-056: The new house's down payment as a debt being paid off

Status: accepted (0.70.0, Nov 2026)

## Context

Hernan, Nov 9 2026: the new house's 30% down payment is a 2,000.00 reserva, a 25,678.22 entrada
and 18 monthly installments of 3,075.36, all paid from Lauren's Produbanco account to the
developer's trust (Fideicomiso Inmobiliario Kalani); two installments are paid. "House payments
is debt payments." The house wasn't on Net worth, its payments had no category of their own, and
debt payments showed only the BIESS loan.

## Decision

- Migration 0040 adds **Housing / New house** (kind debt) and a rule (`KALANI`, contains) that
  sends the trust's lines there. Bank lines already loaded that mention the trust move to it as
  debt payments, each change in audit.change_log.
- It adds the purchase in progress **New house** on Net worth: down payment 83,034.70
  (2,000 + 25,678.22 + 18 × 3,075.36), installment 3,075.36, and a value of 33,829.94 paid so far
  on Nov 9 2026. Later lines in the category add to what's paid (ADR-012's purchase rule). The
  full price isn't known yet, so what's financed at delivery isn't shown; it can be entered on the
  page.
- Saving a loan or a purchase with a savings or spending category makes that category a debt
  category and its lines debt payments (ADR-054 did this once, in migration 0038).
- Lauren's US education loans stay as the workbook has them (Hernan: "keep using what we have"):
  Firstmark's last payment is January 2025 and Nelnet is on hold, so no monthly payment is added.

## Consequences

- Cash flow counts the trust payments as debt payments, not spending or savings; Net worth shows
  what's been paid toward the house as an asset and the rest of the down payment as a commitment.
- If a trust payment's description doesn't mention Kalani, it needs the category by hand.
