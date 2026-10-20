# Statement parsers

One module per source in `api/app/ingestion/parsers/`. A parser takes the PDF's page texts (as
pdfplumber extracts them) and returns `ParsedStatement`: period, opening and closing balance,
printed totals, lines, rejects and tie-out checks. A statement can only be approved when every
check passes and nothing was rejected. Each parser has a golden test on a synthetic PDF with the
real layout (`api/tests/fixtures/statements.py`); real statements are checked locally only
(`tests/unit/test_real_statements.py`).

## Capital One (Venture, `capitalone`) — F4

- **Detect:** `capitalone.com`; card `ending in 4003`; period `Sep 04, 2026 - Oct 03, 2026`.
- **Summary (page 1):** Previous Balance, Payments, Other Credits, Transactions, Cash Advances,
  Fees Charged, Interest Charged, New Balance. pdfplumber interleaves the two columns of page 1, so
  each value is found by its label anywhere in the text.
- **Lines:** per cardholder: `NAME #1234: Payments, Credits and Adjustments` then
  `NAME #1234: Transactions`; each line `Sep 2 Sep 4 UBER EATS SAN JOSE $12.38`; credits print
  `- $4,000.00`. Then `Fees` and `Interest Charged` (`Interest Charge on Purchases $47.63`).
- **Dates:** no year; taken from the billing cycle (a line may fall up to two months before it,
  e.g. `Sep 2` in a `Sep 04 - Oct 03` cycle). December–January cycles are handled.
- **People:** the cardholder name's first matching word (`LAUREN` → Lauren, `HERNAN` → Hernan);
  only the card's last four digits are stored with the line.
- **Signs:** charges are negative (money out), payments and refunds positive. Interest is one
  line on the closing date, type `fee_interest`.
- **Tie-out:** each card's lines = its printed total; all cards = Transactions = Total
  Transactions for the period; payments + other credits; fees; interest; previous − payments −
  credits + transactions + cash advances + fees + interest = new balance; and, when the previous
  statement is loaded, its closing balance = this opening balance.
- **Checked on the real Sep 4 – Oct 3, 2026 statement:** 76 lines (74 purchases, 1 payment,
  1 interest), ties out to 3,932.84.
