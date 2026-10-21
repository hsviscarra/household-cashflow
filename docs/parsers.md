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

## Bank of America (combined statement, `bofa`) — F5

- **Detect:** `bankofamerica.com` / `Bank of America, N.A.`; accounts from page 1
  (`Adv Plus Banking 4460 3033 8872 $6,856.04`, `Regular Savings … 1862`); period
  `for August 22, 2026 to September 22, 2026`.
- **One statement, two accounts.** Each starts at `Account number: 4460 3033 8872` with an
  Account summary (Beginning balance, Deposits and other additions, Withdrawals and other
  subtractions, Checks, Service fees, Ending balance). Continuation pages carry
  `Account # … 8872` in their header. The parser returns each line with its account's last four
  digits and each account's opening and closing balance; both accounts must be linked to the
  statement (they are, by last four digits).
- **Lines:** `08/28/26 Description -25.00`, amounts signed as printed. Descriptions can wrap
  (`ID:9279744380 WEB`); up to two short continuation lines are joined, scam-warning and page
  footer text is not.
- **Sections:** deposits, withdrawals, ATM and debit card subtractions, checks, service fees.
  Service fees load as Financial Costs / Bank Fees.
- **Salary label:** `Transfer Kenility LLC Via WISE … ; "August"` → `pay_reference = August`; the
  deposit still counts in the month it lands (September).
- **Tie-out per account:** each summary figure = its section's lines and printed section total;
  beginning balance + lines = ending balance; and each account's opening balance = its closing
  balance on the previous statement when that statement is loaded. Empty sections are skipped.
- **Checked on the real Aug 22 – Sep 22, 2026 statement:** 9 lines; checking 5,968.07 →
  6,856.04, savings 242.31 → 262.31. Zelle payments and one PayPal purchase have no rule yet.

## Banco Pichincha (Mastercard, `pichincha`) — F6

- **Detect:** `BANCO PICHINCHA C.A.` / `pichincha.com`; card `546605XXXXXX2829`; period on page 2,
  `PERÍODO DESDE PERÍODO HASTA … 13/06/2026 12/07/2026`.
- **Summary:** `MOVIMIENTO 527.69 1,057.81- 574.71 44.59` = saldo anterior, pagos/créditos,
  consumos/débitos, total a pagar (US number format here).
- **Detail:** `DETALLE DE MOVIMIENTOS`: `SALDO ANTERIOR 527,69`, then account-level lines (payments
  `SU PAGO "MUCHAS GRACIAS" 310,00-`, `INTERESES SALDO A FAVOR N/C 0,03-`,
  `INT. FINANCIAMIENTO N/D 0,56`, `ND PRECANCELACION DIF. C. N/D 426,24`,
  `CONT_FIN_SOLCA_C.ROT** N/D 0,02`), then one block per card
  (`… 5466-xxxx-xxxx-6331 * PRINCIPAL REEMPLAZO …`) ending in `SUBTOTAL : 123,75`.
  Lines: `16/06 3541282 UBER *ONE MEMBERSHIP U V CONSUMO NLD 3,99` (operation and country code are
  removed from the description); Ecuadorian number format (`1.057,78`), credits end in `-`.
- **Deferred purchases:** an installment (`2/6`) and a second amount (the deferred balance) may
  follow; the installment amount is the line, the installment is kept as the line's reference and
  the balance in the header totals.
- **Cards:** the replacement card 6331 and the original 2829 both belong to the Pichincha account;
  each line keeps its card's last four digits.
- **Tie-out:** payments and credits; purchases and charges; saldo anterior − credits + debits =
  total a pagar; each card's SUBTOTAL; SUBTOTAL PAGOS; TOTAL CONSUMOS MES (purchases only);
  totals printed in the detail = the summary; continuity with the previous statement.
- **Checked on the real Jun 13 – Jul 12, 2026 statement:** 26 lines, ties out to 44.59; every
  line categorized by the seeded rules.

## Produbanco (savings, `produbanco`) — F7

Hernan's account (•••• 3721) and Lauren's share one layout; the account is chosen by the last four
digits after `CUENTA:`, or Produbanco's only account without digits on file (Lauren's).

- **Detect:** `produbanco.com` / `Banco de la Producción`; `CUENTA: …3721` (only the last four digits are kept);
  period `Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026`.
- **Summary:** `Saldo inicial contable: 297.71`, `Saldo final contable: 6.73`; an optional IVA box
  (`(#) TOTAL BASE IMPONIBLE IVA 15%`, `(#) TOTAL IVA 15%`) is informational only.
- **Detail:** after `Ciudad Fecha Número Descripción Valor Contable Disponible`, one line per
  movement: `Quito Jul 8 100000000004 PAGO IESS BANCA EN LINEA -100.00 1,849.59 1,849.59` (city,
  Spanish month and day, number, description, signed amount, book balance, available balance).
  Numbers may contain `X` or `-` (`400000XXXXXX0001`, `20000000-0001`); `# ` before a description
  marks a fee that carries IVA and is removed.
- **Sections:** `TARIFA …` → fee (Bank Fees); `PAGO TARJETA CREDITO …` → card payment;
  `CAPITALIZACION DE INTERESES …` → Interest Earned; everything else is a movement classified by
  merchant rules.
- **IESS and BIESS:** both print as `PAGO IESS BANCA EN LINEA`; staging splits them by amount
  (under 300 → Household Staff / Empleada IESS, otherwise Housing / Mortgage BIESS) until rules can
  carry amount ranges (F9).
- **Tie-out:** opening + lines = closing; every printed running balance equals the previous one
  plus the line (the total gap must be 0.00); continuity with the previous statement.
- **Checked on the real Jun, Jul and Aug 2026 statements:** 17, 10 and 15 lines; Jul ties 297.71
  to 6.73, and each month opens at the previous month's close. Interbank transfers (empleada,
  condo fee, office rent in, Dad's insurance) still need a category: F9 rules and F10 matching.
