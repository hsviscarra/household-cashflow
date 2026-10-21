# ADR-005: Statements that arrive as pictures are read with local OCR, guarded by the tie-out

- Status: accepted
- Date: 2026-10-21

## Context

Pacificard (Banco del Pacífico's Mastercard) only offers its statement as a web page. Saving it
gives a PDF that holds one screenshot (880 px wide, about 108 ppi) with a grey "COPIA" watermark
across the text. There is no text layer, so the text parsers can't read it.

Options: OCR in the app; the Claude API with the page image (cents per statement, the statement
leaves the server, needs a confirmation step); or asking for a text export the bank doesn't offer.

## Decision

- Tesseract runs inside the app's container (`tesseract-ocr` in the image and in CI). Nothing
  leaves the server. Hernan chose this option on 2026-10-21.
- `app/ingestion/ocr.py` reads in two passes: the whole statement area at 4× with the watermark
  thresholded away, then every amount and date again from the original picture with a restricted
  alphabet at several sizes and thresholds, taking the reading most of them agree on. Only the part
  above the second-page banner is read (the fine print below is slow to read and not needed).
- Upload recognizes a picture-only PDF with a quick OCR of its header; "Read lines" runs the full
  OCR (15–60 s, shown on the Import page).
- The parser takes each printed total from the value most of its printings agree on, and the usual
  tie-out (lines against subtotals, previous + purchases − payments + charges = total due,
  continuity) blocks any statement where a digit was still misread.

## Consequences

- The image grows by about 40 MB; reading a Pacificard statement takes tens of seconds of CPU,
  acceptable for a few statements a month. If Azure's small CPU makes it too slow, reading can move
  to a background task.
- Descriptions under the watermark can carry OCR noise ("CARGO. “APITA'"); amounts and dates can't,
  because of the tie-out. Merchant rules match on words that survive (e.g. "FINANC.SOLCA").
- Any other picture-only statement can reuse `ocr.ocr_pages` with its own parser.

## Update 2026-10-21: OCR is the fallback for every bank

Hernan expects real PDFs from every bank but wants OCR as the default when a PDF has no text (a
scan, or a statement saved as a picture):

- Upload: a PDF without text is recognized by OCR of its header, then of the whole first page (a
  scan's bank name may be in the footer, as Produbanco's is).
- "Read lines": when a bank's PDF has no text layer, its own parser gets the OCR text instead.
- The OCR step adapts to the picture: pages are enlarged to about 3,500 px wide (4x a screenshot,
  2x a 200 dpi scan) and each number is re-read at text heights of 32–56 px; amounts keep their
  sign, their "$" and their decimal mark (1,057.81 or 1.057,78), and an amount can't start with
  "00".
- Parsers that relied on accents (Diners) match without them; Produbanco recovers a sign OCR lost
  from the running balance; Pacificard settles a tie between two printings of a total with the
  printed value the lines balance with.
- Checked with 200 dpi scans of the synthetic statements of all five text banks (each ties out)
  and the five real Pacificard statements. Photos (JPG/HEIC) are still refused; a tilted or
  shadowed photo would need straightening first.
