# ADR-105: Parsers split into readers, checked against real statements

Status: accepted (0.114.0, Nov 2026). No schema change, no change in what any statement reads as.

## Context

After ADR-103, 12 functions were left over the size limits, all in reading statements and the
workbook: each parser's `parse` (BofA, Capital One, Diners, Pacificard, Pichincha card and
account, Produbanco account and Visa, plus Produbanco's balance chain), `stage.parse_statement`
and the workbook's `_parse_sheet` and `_checks`. They are the code where a careless split costs
most: a line read differently changes the household's numbers.

## Decision

- **One shape for every parser.** `parse` now reads as its steps: the header (period, summary)
  as small functions that raise `ParseError`; a `_Reader` that keeps the state the old loop kept
  in local variables (account, section, card, block) and tries one small `_take_*` method per
  kind of line; the checks as their own function. Pacificard, read with OCR, does it in two
  passes (`_Scan`, then the rows). `base.numbered_lines` gives every parser the same page and
  line numbers.
- **Staging** is `_read`, `_accounts_of`, `_save_header`, `_new_batch`, `_stage_lines` and
  `_mark_duplicates`; its imports inside functions became ordinary ones.
- **The workbook** is a `_SheetReader` (main blocks, then side tables) and a `_block_check`.

## How it was verified

Behaviour was required to stay byte-for-byte the same, checked three ways after each parser:

1. the golden tests (synthetic statements, in CI);
2. the household's real statements kept in the working session (24 PDFs across all eight
   formats, including three with OCR'd rejects and five that fail to parse on purpose) and the
   Cash Flow workbook, parsed before and after and compared as JSON: identical;
3. a differential run of the old and new parsers over 11,778 inputs (the real pages, the
   synthetic fixtures and 150 seeded mutations of each: lines dropped, repeated, swapped,
   truncated, digits and tokens changed): identical results, errors included.

The real files never leave the session and are not in the repository.

## Consequences

- No function in the API carries a size exception; CI holds the limits everywhere.
- A new bank format is a new module of the same shape: a header, a `_Reader` with one method per
  kind of line, and its checks.
