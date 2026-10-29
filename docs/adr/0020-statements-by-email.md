# ADR-020: Statements arrive by email, through a Gmail Apps Script and a token-protected inbox

- Status: accepted
- Date: 2026-10-29

## Context

F20 (issue #56): bank statements reach Hernan's Gmail every month, and uploading each PDF by hand
is the slowest step of the month. It is done when a statement emailed to Gmail appears on the
Import page, read and waiting for approval, without a manual upload.

Today's senders, all with the PDF attached and no password:
- Banco Pichincha, `documentoselectronicos@pichincha.com`: savings account ("NOTIFICACION DE
  ESTADO CUENTA") and credit card ("Notificación de Estados de Cuenta de Tarjeta de Crédito").
  The same sender also emails invoices, which are left out.
- PacifiCard, `estadodecuenta@pacificard.ec`: "Estado de Cuenta PacifiCard - Corte MM/YYYY".
- Diners Club, `info@efacturacioninterdin.com`: "Estado de cuenta Diners Club".

Bank of America and Capital One will follow once their emails are turned on (issue #60).

Options considered:
- **The app reads Gmail through Google's API.** That needs an OAuth app in Google Cloud, a refresh
  token for Hernan's whole mailbox stored in Azure, and a scheduled job.
- **Claude reads Gmail through its connector.** The connector can't download attachments, and it
  would need the Mac on, like the IBKR task.
- **A Google Apps Script in Hernan's Gmail pushes the PDFs to the app.** It runs on Google's
  servers on an hourly trigger, needs no Google Cloud project, and Gmail access never leaves
  Google. The app only receives files.

## Decision

- **Apps Script** (`infra/gmail/Code.gs`), pasted once into script.google.com under Hernan's
  account. Every hour it:
  - searches each bank's sender and subject, for emails from the last 45 days that have a PDF
    and aren't labeled yet;
  - posts each PDF attachment to the app;
  - labels the email `cashflow-imported` (read, or already in the app) or `cashflow-check` (it
    needs a person on the Import page, or the app refused it).

  An email the app couldn't take, because the app or the database was asleep, is left unlabeled
  and tried again next hour. `backfill()` does the same since a chosen date, for the backlog.
- **`POST /api/inbox`** (multipart: `file`, `sender`) is protected by its own bearer token
  (`INBOX_TOKEN`). It's excluded from the Microsoft sign-in like `/mcp`, and the token opens
  nothing else. Each file goes through the upload path unchanged:
  - it is hashed, and a file already uploaded is a duplicate, so retries are harmless;
  - it is stored and its bank detected;
  - when its account is known, it is read into a batch with the tie-out and continuity checks;
  - the batch waits on the Import page. Nothing reaches the transactions without Hernan's approval.

  The answer is always 200 with an outcome, so the script knows what to do.
- **Traceability.** The statement's and the batch's `uploaded_by` / `created_by` is
  `gmail (<sender>)`, so the Import page shows where each file came from.
- **Passwords.** None of the current banks protect their PDFs. An encrypted PDF is refused, as an
  upload is, and gets the `cashflow-check` label. Support for passwords can come with the bank
  that needs it.
- **Setup:** `infra/azure/setup-inbox.sh` creates the token as a Container App secret, excludes
  the path from sign-in, and checks it. `main.bicep` and `bootstrap.sh` carry the token on
  re-runs, and `setup-mcp.sh` keeps the path excluded.

## Consequences

- No new schema, job or Google Cloud project; the hourly run costs nothing.
- The token can post files but not read or approve anything. Anyone holding it could fill the
  Import page with files waiting for approval; rotate it with `ROTATE=1`.
- A bank that changes its sender or subject stops arriving silently. The month-status page's
  missing-statement check shows it.
- Lauren's statements (issue #61) can use the same script in her own Gmail, with its own token,
  or a forward to Hernan's.
