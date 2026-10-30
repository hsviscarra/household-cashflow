# ADR-021: Purchases product by product, from SRI electronic invoice XMLs

- Status: accepted
- Date: 2026-10-30

## Context

F21 (issue #57): groceries are one of the biggest expenses, mostly weekly at Supermaxi, and the
card statement only shows one total per visit. Ecuadorian vendors must issue an electronic invoice
("factura") to the buyer's cédula, authorized by the SRI. Its XML lists every product with
quantity, unit price, discount, tax and total. Vendors email it with a PDF copy: Corporación
Favorita from `infoedoc@favorita.com.ec`, and also internet, phone, pharmacy, school and others.
The SRI "Comprobantes recibidos" list (.txt) has only totals and each invoice's 49-digit access
key, not products.

Scanning paper receipts (OCR) was the first idea. XML is exact, needs no camera, and is already in
Gmail.

## Decision

- **Source: the invoice XML.** Two ways in:
  - the Gmail script (ADR-020) also sends every `.xml` attachment from any sender, through the
    same `/api/inbox` with the same token; the inbox reads an XML as an invoice and a PDF as a
    statement;
  - or XMLs uploaded on the new **Purchases** page (downloaded from SRI en línea or a vendor's
    site).

  Lauren's invoices come by a Gmail filter that forwards them to Hernan's Gmail; a filter keeps
  the vendor as the sender.
- **Reading.** `defusedxml` refuses entity expansion and external entities. The reader takes
  either the authorized wrapper (`<autorizacion><comprobante><![CDATA[<factura>…`) or a bare
  `<factura>`, and ignores namespaces. Only `codDoc` 01 (factura) is read; credit notes and
  retentions are skipped, not refused. The lines must add up to the invoice's
  `totalSinImpuestos` within 0.02, or the invoice is refused.
- **Stored** in `core.invoice` and `core.invoice_line` (migration 0022), keyed by the access key,
  so the same invoice again is a duplicate.
  - Kept: issuer RUC, name, number, date, totals.
  - Not kept: the buyer's identification and address.
- **Matched** to the transaction that paid it: the same amount, one day before to four days after
  the invoice date, and not already matched. Two or more candidates are left unmatched; nobody
  guesses. Invoices usually arrive before the card statement, so opening the Purchases page
  matches the ones still waiting.
- **Product groups.** The groups are a fixed list of 17, separate from the transaction categories:
  Meat & Fish, Dairy & Eggs, Fruit & Vegetables, Bakery, Pantry, Snacks & Sweets, Drinks, Alcohol,
  Frozen & Ready Meals, Baby, Household & Cleaning, Personal Care, Health & Pharmacy, Pets,
  Services, Car, Other. In order:
  1. a confirmed product rule (`core.product_rule`, by normalized description);
  2. a few unambiguous Spanish keywords, whole words only;
  3. Claude's suggestion on request. Only the product descriptions are sent: no vendor, amounts
     or people.

  Keyword and Claude groups count in the month's totals but stay on the "needs a group" list
  until a person confirms them. Confirming saves a rule for that product.
- **Claude reads it.** `mart_reader` gets SELECT on `core.invoice` and `core.invoice_line`, but
  not the rules. The MCP tool `purchases(month)` returns spending by group, top products and
  vendors.

## Consequences

- Only purchases invoiced to a cédula whose email reaches Gmail appear. In 2026 most Supermaxi
  visits weren't, so Hernan is making sure his cédula and email are given at checkout. The page
  says so instead of implying it's all the spending.
- Product groups explain *what* inside a transaction's category: Groceries stays the category,
  and Purchases splits it. Nothing in the cash flow changes.
- The SRI list's access keys could later fetch missing XMLs from SRI's public authorization
  service. This environment couldn't reach SRI to verify it, so it's left for a follow-up.
