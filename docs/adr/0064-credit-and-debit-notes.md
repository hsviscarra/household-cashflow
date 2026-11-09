# ADR-064: Credit and debit notes in the IVA return; no comparisons for an unfinished month

Status: accepted (0.76.0, Nov 2026)

## Context

Hernan (Nov 9 2026): the SRI also has notas de débito (and crédito) that matter; and Spending said
"In November 2026 you spent 516.06: 90% less than October" on November 9, comparing nine days with
whole months.

## Decision

- Migration 0044: **core.tax_note**, notas de crédito (codDoc 04) and débito (05) issued by the
  household or received by it. Uploads and the SRI list read them.
- The month's Form 104: 411 = 401 − credit notes issued + debit notes issued (base); 510 = 500 −
  credit notes received + debit notes received, counting only received notes from issuers marked
  business. IVA (421, 520) is 15% of the net base. Notes are listed on the page and in the
  workbook. Notes carried to the next month (fields 442–444, 543–544) aren't modelled: a note
  counts in the month it's issued.
- Spending for the current month says "So far in November 2026 (day 9) you spent …" with no
  comparison, its KPI says the month isn't over, and the table's previous-month column says
  "(whole month)".

## Consequences

Guías de remisión and liquidaciones de compra are still skipped. Other partial-month
comparisons should follow the same rule.
