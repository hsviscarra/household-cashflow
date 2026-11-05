# ADR-023: People and transfer notes

Status: accepted (0.37.0, Nov 2026)

## Context

Ecuadorian bank statements print a transfer as "TRANSFERENCIA" with no name and none of the
description typed when it was sent. Some money in Hernan's accounts isn't his: Rubén's payments
arrive in Hernan's Bank of America and Produbanco accounts, and Hernan pays Rubén's suppliers from
them. Rules can't tell those lines apart, and pairing them as transfers between own accounts
(received for Rubén on Monday, paid out for him on Tuesday) is wrong.

The banks' emails do carry the missing facts: Produbanco's "Transferencia enviada / recibida"
names the other party, the amount, the account's last 4 and the description; Pichincha's
"NOTIFICACION" names the recipient and the concept.

## Decision

- **People** (`core.counterparty`): a name, texts to find in statement descriptions ("RUBEN
  MIRANDA; NAPOLES TRANSPORT"), a category (usually Transfers / Held for Others) and optionally a
  personal-loan item on Debt & Net Worth. A statement line whose description contains a text gets
  the person (`core.transaction.counterparty_id`) and their category.
- **Transfer notes** (`core.transfer_note`): date, signed amount, optional account, person,
  category, the other party's name and the description. Typed on the People & Transfers page or,
  next, read from the banks' emails (deduplicated by the bank's reference). A note matches the
  statement line with the same amount, in its account when it has one, at most 5 days apart,
  closest first, one line per note. The line gets the person, the note's category (else the
  person's) and the description in its notes.
- **Precedence:** a category chosen by hand (manual, accepted suggestion, split, workbook) is never
  changed; a note or a person overrides a rule or a statement section. Notes run before people's
  texts, both after each approved statement, when a note or person is saved, and on demand.
- **Balance:** a person linked to a personal-loan item moves it: its latest value plus their
  transfer lines after it (received for them raises what is held, paid out for them lowers it).
  "Holding for Rubén" is created from the page with an opening amount.
- **Transfers:** lines with a person, and transfer categories other than card payments, moves
  between own accounts and the Transfers group, are never paired or listed as missing their other
  side.
- **Data Status** lists notes whose account's statement covering their date (plus 5 days) is
  loaded but which found no line.
- **Privacy:** names, amounts, dates and descriptions only; no account numbers or cédulas. The
  read-only login can read both tables for Claude's data_status tool.

## Consequences

- Most anonymous transfers are named without typing once the email reader is in place; manual
  notes cover the rest.
- Deleting a note or a person never changes a line's category; the line only loses the link or
  name.
- The import preview doesn't show note matches yet: they apply when the statement is approved.
