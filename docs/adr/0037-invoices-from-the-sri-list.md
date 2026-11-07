# ADR-037: Invoices from the SRI's list of received documents

Status: accepted (0.53.0, Nov 2026)

## Context

Phase 1 of the improvement plan. The Gmail script brings in only the invoices that vendors email
to Hernan's address (ADR-021). Shops that don't email, invoices sent to Lauren's address that
she doesn't forward, and pharmacies where only the cédula was given are missing, and they count
for gastos personales (ADR-036). SRI en línea lists every document issued to a cédula
("Comprobantes electrónicos recibidos") and lets you download the list, which carries each
document's 49-digit access key but not its products. Signing in to SRI en línea automatically
would mean storing the SRI password and getting past the portal's sign-in.

## Decision

- **No robot, no SRI password.** A person downloads the month's list in SRI en línea (or copies
  it) and uploads or pastes it on Purchases.
- `POST /api/invoices/sri/keys {text}` finds every distinct 49-digit access key, whatever the
  file's layout, and sorts them into new invoices, invoices already in the app, and other
  documents (credit notes, retentions: digits 9-10 of the key aren't `01`), which are skipped.
- `POST /api/invoices/sri/fetch {keys}` (at most 10 per call; the page sends batches) asks the
  SRI's public authorization web service (`AutorizacionComprobantesOffline`, operation
  `autorizacionComprobante`, setting `SRI_AUTHORIZATION_URL`) for each key. An authorized
  answer goes through the same reader and store as an upload, so the buyer becomes Hernan or
  Lauren (ADR-036), the payment is matched and the products are grouped. "Not found", "not
  authorized", "still processing" and an unreachable SRI are reported per key, and nothing is
  stored for them.
- Only access keys are sent to the SRI. Calls use the standard library (`urllib`), a 20-second
  timeout and a 2 MB limit on the answer.

## Consequences

- A month takes two minutes of a person's time: download, upload. The SRI's service is slow at
  times; a key that fails can be sent again later (keys already in the app are skipped).
- If the SRI ever puts the service behind a sign-in, uploading the XMLs downloaded from SRI en
  línea still works.
