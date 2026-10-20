# ADR-003: Storing and detecting uploaded statements

- Status: accepted
- Date: 2026-10-20

## Context

Hernan and Lauren upload bank and card statements every month, and later several years at once.
The same PDF is often downloaded twice under different names. Statement PDFs hold personal data
(names, addresses, cédula, full account numbers) that must not reach the database or git.

## Decision

- **Content-addressed files.** Each upload is hashed (SHA-256). A known hash is reported as
  "Already uploaded" and not stored again. Files are kept as `<source>/<sha256>.pdf` in the private
  `statements` Blob container (managed identity, no keys) or, locally, in `STATEMENTS_DIR`.
- **Metadata only in SQL.** `raw.statement_file` keeps the hash, file name, size, pages, detected
  source, the last four digits found, the period when the layout shows it, the storage key and who
  uploaded it. Text read from the PDF is used for detection and then discarded.
- **Fingerprints are domains and legal names** (`bankofamerica.com`, `capitalone.com`,
  `BANCO PICHINCHA C.A.`, `produbanco.com`, `dinersclub`), never merchant text, because a BofA
  statement mentions "CAPITAL ONE" in its payment lines.
- **Account matching:** last four digits; else the bank's single account without digits on file
  (Lauren's Produbanco); else the bank's only account (the replacement Pichincha card 6331); else
  Hernan chooses. The match type (`last4`, `by_bank`, `manual`) is recorded and shown.
- **Refuse what can't be read:** password-protected PDFs get a message asking for an unlocked copy;
  the app never asks for or stores a statement password.

## Consequences

- Re-uploading the same file is harmless; a re-download from the bank with different bytes is a new
  file, and line-level duplicates are caught later by each transaction's natural key (F4 on).
- Parsers (F4 to F8) read the stored file again from storage, so detection can stay shallow.
