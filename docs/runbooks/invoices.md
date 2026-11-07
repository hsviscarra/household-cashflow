# Purchases from electronic invoices

The **Purchases** page breaks a month's shopping into products: what was bought at Supermaxi, the
pharmacy, the workshop and so on, grouped as Meat & Fish, Dairy & Eggs, Baby, Household & Cleaning
and more (F21, ADR-021).

## How invoices get in

- **By email (usual).** The Gmail script (docs/runbooks/gmail-statements.md) sends every invoice
  XML it finds, from any vendor, once a day. After updating `Code.gs` in the script editor to
  this version, run `backfill` once to send this year's invoices.
- **By upload.** On Purchases, choose **Upload invoice XMLs**. For example, download the XMLs from
  SRI en línea (Facturación electrónica → Comprobantes electrónicos recibidos) or from
  cfavorita.ec/felectronica.
- **Lauren's invoices.** In her Gmail, add a filter for `from:infoedoc@favorita.com.ec`, plus any
  other vendor, that forwards to hsviscarra@gmail.com. Use a filter, not the Forward button, so
  the vendor stays the sender.

An invoice already in the app is skipped, so sending one twice is harmless. Credit notes and
retentions are skipped too.

## Getting every Supermaxi purchase

Only purchases invoiced to your cédula, with your email on file at Favorita, reach Gmail. At
checkout, give your cédula every time. Check cfavorita.ec/felectronica to see every invoice issued
to your cédula and the email Favorita has for you.

## Grouping products

- A few obvious products are grouped by keyword (LECHE → Dairy & Eggs, DETERGENTE → Household &
  Cleaning). They still appear under "needs a group" until you confirm them.
- **Ask Claude about N products** suggests a group for the rest. Only the product descriptions
  are sent.
- **Save group** confirms it. The same product gets that group on every invoice, now and later.

## Matching to the card

Each invoice is matched to the line that paid it: the same amount, from a day before to four days
after the invoice date. "Payment not found yet" usually means that month's card statement isn't
loaded yet; the match happens when you open the page after it is. Two purchases with the same
amount on nearby days aren't matched automatically.

## Claude

Claude can answer "what did we spend on baby things in October?" with the `purchases` tool of
the household-cashflow connection.

## Gastos personales (ADR-036)

The **Gastos personales** page (Plan) adds up each person's deductible invoices for the tax year,
against the cap their cargas familiares allow, and estimates the 18% rebate.

- **Whose invoice.** Run `./infra/azure/setup-buyers.sh` once: it asks for both cédulas and keeps
  them only as a Container App secret (`INVOICE_BUYERS`). New invoices are then assigned to Hernan
  or Lauren as they're read; the database keeps the name, never the number. Invoices already in the
  app take the person of the card line that paid them, or the one you choose on the page.
- **Category.** SRI's six: Vivienda, Educación (arte y cultura), Salud, Alimentación, Vestimenta,
  Turismo. Guessed from the line that paid it (Supermarket → Alimentación, Pharmacy → Salud…) or
  the products; "All from this issuer" saves the choice for every invoice from that RUC.
  "Not deductible" leaves an invoice out.
- **Cargas.** Set them per person and year on the page; they raise the cap (7 baskets with none,
  9, 11, 14, 17, then 20; 100 for a catastrophic, rare or orphan illness).
- **The annex.** "Numbers for the annex (CSV)" lists RUC, provider, category, invoices, base and
  total per issuer. Amounts are before IVA; confirm with your accountant before filing.
- **A new year.** Add the SRI's basic basket (canasta básica familiar) for the year to `CANASTA`
  in `api/app/services/gastos.py`; until then the page shows totals without a cap.
