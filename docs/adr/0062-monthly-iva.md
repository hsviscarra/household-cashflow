# ADR-062: The monthly IVA return from the SRI documents

Status: accepted (0.74.0, Nov 2026)

## Context

Hernan invoices his work with IVA and an accountant prepares his monthly IVA return: a workbook of
sales (with the retenciones clients made), purchases with IVA credit and personal expenses, and
Form 104. He asked whether the app could produce the same from the SRI's documents. Checked
against his September 2026 workbook and declaration (in the session only): every figure comes
from issued invoices, received invoices and comprobantes de retención.

## Decision

- Migration 0043: **core.sale_invoice** (invoices the household issued: the issuer's RUC is a
  household cédula + 001), **core.withholding** (comprobantes de retención made to the household,
  versions 1 and 2: income tax and IVA withheld, the period and the invoice withheld on) and
  **core.tax_issuer_rule** (an issuer's invoices count as business, personal or neither).
  Issued invoices never enter core.invoice, so purchases, groceries and deductions don't see them.
- Uploads and the SRI list import read issued invoices and retenciones too (codDoc 07 is fetched).
- `services/iva.py` builds a person's month: sales, received invoices with how they count (the
  issuer's rule, else personal when the invoice has a deduction category, else unclassified),
  retenciones, and Form 104: 401/421 (IVA = 15% of the taxed base, as declared), 500/520, 601/602,
  605/606 carried from the previous month, 609, 615/617 carried to the next, 620/902 to pay. The
  first month's carried credit is entered once (`core.app_setting` `iva-opening:<person>`).
- **Taxes → Monthly IVA** shows the month, asks for the carried credit once and how each new
  issuer counts, and downloads the accountant's workbook (sales, COMPRAS 15%, GASTOS PERSONALES,
  and a Formulario 104 sheet). Filing stays in SRI en línea.

## Consequences

Covers a person who invoices services at 15% without imports, exports, fixed-asset sales or
proportional credit; credit notes are not read yet. The accountant should compare the first
months. Reproduces September 2026 exactly (466.84 caused, 1,417.26 carried, 0 to pay).
