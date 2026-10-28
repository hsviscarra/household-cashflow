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

## Banco Pichincha (bank account, `pichincha`) — F19

Same source as the card. Detection tells them apart by the summary's "CHEQUES / DÉBITOS"
(`Detection.kind` is "bank"), and account matching then only considers non-card accounts, so an
account statement never lands on the Mastercard.

- **Page 1:**
  - "FECHA ÚLTIMO CORTE (FACTURA) 07-08-2026" and "FECHA ESTE CORTE 04-09-2026". The period runs
    from the day after the last cut to this one.
  - "CUENTA 9999990001" (only the last four digits are kept).
  - The summary: "SALDO ANTERIOR", "DEPÓSITO / CRÉDITOS (n) total", "CHEQUES / DÉBITOS (n) total",
    "SALDO ACTUAL".
- **"DETALLE DE MOVIMIENTOS":** one line per movement, for example
  "18-ago. 12 1002 TRANSFERENCIA INTERBANCARIA RECIBIDA 0.00 100.00 90.00". The columns are
  day-month (Spanish), branch, document number, description, debit, credit and running balance,
  in US amount format. The year comes from the period.
- **Fees:** "**COMISION …" and "IVA COBRADO" lines.
- **Checks:**
  - opening balance plus lines equals closing balance;
  - no gaps in the running balance;
  - credits and debits each match the summary's total and count.

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

## Diners Club (`diners`) — F8

Hernan's and Lauren's statements share one layout. Neither account has card digits on file, so the
account is chosen by the main cardholder's name on the `* PRINCIPAL` card line (Hernan or Lauren).

- **Detect:** `dinersclub` / `Diners Club`; cards `0036-xxxx-xxxx-1234` (every card on the
  statement); period on page 1, `04 JUN 2026 AL 03 JUL 2026` (Spanish months).
- **Summary (page 1):** one figure per line, other text may follow on the same line:
  `SALDO ANTERIOR: 708,82`, `PAGOS/CRÉDITOS: 708,82-`, `CONSUMOS: 439,81`, `DÉBITOS: 0,00`,
  `Total a pagar: 439,81`. Ecuadorian number format throughout.
- **Purchases:** `Consumo período actual`, one block per card (`NAME 0036-xxxx-xxxx-1234 *
  PRINCIPAL …` or `* ADICIONAL`) ending in `SUBTOTAL DE CONSUMOS:`, then
  `TOTAL DE CONSUMOS: <purchases> <remaining deferred balance>`. A line is
  `26/06 10001 TIENDA DE PRUEBA 17,25`; a deferred purchase adds its installment and remaining
  balance: `10/11 1 COLEGIO DE PRUEBA CUMBAYA (8/12) 300,00 1.200,00`. The installment keeps the
  original purchase date; when that is before the period, the line is dated on the closing date
  (the month it is billed) and `8/12` is kept as its reference.
- **Debits and credits:** `Detalle débitos y créditos` (may continue on the next page):
  `DETALLE DE DÉBITOS` (`INT. FINANCIAMIENTO N/D`, `INTERESES DE MORA N/D`,
  `GASTO GESTION COBRANZAS N/D T15`, `CONT_FIN_SOLCA_C.ROT** N/D`), `DETALLE DE PAGOS Y CRÉDITOS`
  (`SU PAGO "MUCHAS GRACIAS" 708,82-`), up to `TOTAL A PAGAR:`.
- **Ignored:** `Consumo en el exterior` repeats foreign purchases already listed (AWS); the
  interest, minimum-payment and fee tables on pages 4–6.
- **Sections:** payment, interest (financing and late interest), fee (collection fee), charge
  (SOLCA, IVA withheld), purchase.
- **Tie-out:** purchases, charges and payments against the summary; previous − payments +
  purchases + charges = total due; each card's subtotal; each cardholder in `Resumen consumos por
  cliente`; totals printed in the detail; the remaining deferred balance; continuity with the
  previous statement.
- **Checked on the real Jul, Aug and Oct 2026 statements:** 9, 9 and 6 lines, every check passes.
  September is missing, so October's opening isn't compared (a gap is no longer treated as a
  mismatch). August shows a late-payment interest and a collection fee (10.81 together).

Continuity (all sources): the opening balance is compared only with a statement that ends within
a week of this one's start; a missing month is left for the data status page (F12).

## Scans of any bank (OCR fallback) — 0.9.2

A PDF without a text layer is read with OCR (ADR-005) and goes to the bank's own parser, so the
same tie-out applies. Diners labels match without accents; Produbanco takes a sign OCR lost from
the running balance. Reading takes about 15–20 s per statement.

## Pacificard (Banco del Pacífico Mastercard, `pacificard`) — F8b

The statement is a screenshot of the bank's web page saved as PDF (no text, grey "COPIA"
watermark), read with OCR (ADR-005). One account: Pacificard Mastercard Black (Hernan, with an
additional card for Lauren). The card is printed `NNNN-NNXX-XXXX-XNNN`: only three digits, so no
last four are stored; the statement is matched as Pacificard's only account.

- **Detect:** a quick OCR of the page header; `pacificard` / `pacifico.fin.ec` /
  `Banco del Pacifico S.A.`; period `Periodo de corte desde: 25/AGO/2026 hasta 24/SEP/2026`.
- **Summary:** `RESUMEN DE MOVIMIENTOS` prints previous debt, purchases and debits, payments,
  interest and charges, total debt (`400.00 148.85 80.00 4.10 472.95`); `Deuda Total X 100% X`.
- **Detail:** `DETALLE DE MOVIMIENTOS DEL PERIODO`: `****** SALDO ANTERIOR 400.00`, a block per
  cardholder (`<id> NAME`, local purchases then `DETALLE DE CONSUMOS EN EL EXTERIOR`), lines
  `SEP/08 100002 SU PAGO PAGO DIRECTO BDP GUAYAQUI PAGO 80.00 -`: date (Spanish month/day),
  reference, description, operation (`CONS`, `PAGO`, `INT`, `CARG`, `N/D`, `N/C`), US$ amount,
  foreign amount for purchases abroad, `+` (adds to the debt) or `-`. Then `TOTAL PAGO DE
  CONTADO`, `SALDO ACTUAL ROTATIVO`, `SALDO ACTUAL DIFERIDO`, `SUBTOTAL CONSUMOS PERIODO`,
  `SUBTOTAL PAGOS/CREDITOS`.
- **OCR noise handled:** months `4GO`/`AG0` (AGO), days `0S` (05), operations `Cons`, `CONS3`,
  `W/D`, `N/D-`; cardholder names `HERWAN`, `LAUREW`; an unreadable start date falls back to the day
  after the same day a month before the cut. Amounts and dates are re-read digits-only (ADR-005).
- **Sections:** payment; interest (`CARGOS CAPITAL ANTERIOR`); fee (`GESTION DE COBRANZA`,
  foreign-purchase commission, card renewal); charge (SOLCA, `SEG. DESGRAVAMEN` credit-life
  insurance, IVA on digital services); purchase.
- **Tie-out:** purchases and debits = `SUBTOTAL CONSUMOS`; payments = `SUBTOTAL PAGOS`; interest
  and charges = the summary; previous + purchases − payments + charges = total due (each total is
  the value most of its printings agree on); no deferred balance (not seen yet: a statement with
  one stops instead of loading wrong); continuity.
- **Checked on the real statements Apr 25 – Sep 24, 2026 (five months):** 8, 6, 6, 8 and 9 lines,
  all tie out and chain month to month; about 15–20 s each to read.
