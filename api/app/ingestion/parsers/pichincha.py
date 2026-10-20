"""Banco Pichincha Mastercard statements, in Spanish (F6).

Page 2 has the period ("PERÍODO DESDE PERÍODO HASTA … 13/06/2026 12/07/2026") and the summary
("MOVIMIENTO 527.69 1,057.81- 574.71 44.59": saldo anterior, pagos/créditos, consumos/débitos,
total a pagar). "DETALLE DE MOVIMIENTOS" lists account-level lines first (payments, interest,
early payoffs of deferred purchases, SOLCA), then one block per card ("NAME 5466-xxxx-xxxx-6331
* PRINCIPAL …") ending in "SUBTOTAL : 123,75". A line is "16/06 3541282 UBER *ONE MEMBERSHIP U V
CONSUMO NLD 3,99"; credits end in "-". Amounts use the Ecuadorian format (1.057,78) in the detail
and the US format (1,057.81) in the summary. A deferred purchase may print a second amount (the
deferred balance) and an installment ("1/6"). Layout notes in docs/parsers.md.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError, Reject

NAME = "pichincha"
NUM = r"[\d.,]+[.,]\d{2}-?"

PERIOD = re.compile(r"(\d{2}/\d{2}/\d{4}) (\d{2}/\d{2}/\d{4})")
SUMMARY = re.compile(rf"^MOVIMIENTO ({NUM}) ({NUM}) ({NUM}) ({NUM})$")
CARD = re.compile(r"^(?P<name>[A-ZÁÉÍÓÚÑ ]+?) \d{4}-x{4}-x{4}-(?P<card>\d{4})\b", re.IGNORECASE)
LINE = re.compile(
    rf"^(?P<d>\d{{2}}/\d{{2}}) (?:(?P<ref>\d{{3,}}) )?(?P<desc>.+?) "
    rf"(?:(?P<cuota>\d{{1,2}}/\d{{1,2}}) )?(?P<amt>{NUM})(?: (?P<dif>{NUM}))?$"
)
OPERATION = re.compile(r" (?P<op>CONSUMO|N/D|N/C)(?: (?P<ctry>[A-Z]{3}))?$")
SUBTOTAL_CARD = re.compile(rf"^SUBTOTAL : ({NUM})$")
SUBTOTAL_PAYMENTS = re.compile(rf"^SUBTOTAL PAGOS ({NUM})$")
TOTAL_PURCHASES = re.compile(rf"^TOTAL CONSUMOS MES ({NUM})$")
TOTAL_DUE = re.compile(rf"^TOTAL A PAGAR USD ({NUM})$")
PREVIOUS = re.compile(rf"^SALDO ANTERIOR ({NUM})$")
DETAIL_END = ("TOTAL A PAGAR USD", "PAGO MINIMO")
PEOPLE = {"HERNAN": "Hernan", "LAUREN": "Lauren"}


def amount(text: str) -> Decimal:
    """'1.057,78' or '1,057.81' or '310,00-' → Decimal; a trailing '-' is a credit."""
    neg = text.endswith("-")
    t = text.rstrip("-")
    # Ecuadorian "1.057,78" swaps the separators; US "1,057.81" only drops the commas.
    t = t.replace(".", "").replace(",", ".") if t[-3] == "," else t.replace(",", "")
    value = Decimal(t)
    return -value if neg else value


def _date(day_month: str, start: date, end: date) -> date:
    for year in (end.year, end.year - 1):
        d = datetime.strptime(f"{day_month}/{year}", "%d/%m/%Y").date()
        if start - timedelta(days=62) <= d <= end + timedelta(days=7):
            return d
    raise ValueError(f"{day_month} is outside the statement period")


def _section(desc: str, op: str | None) -> str:
    upper = desc.upper()
    if upper.startswith("SU PAGO"):
        return "payment"
    if "INT. FINANCIAMIENTO" in upper or upper.startswith("INTERESES"):
        return "interest"
    if op == "CONSUMO":
        return "purchase"
    return "charge"  # SOLCA, RET IVA, early payoffs and other N/D / N/C lines


def parse(pages: list[str]) -> ParsedStatement:
    text = "\n".join(pages)
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Period (PERÍODO DESDE … HASTA) not found.")
    start = datetime.strptime(m.group(1), "%d/%m/%Y").date()
    end = datetime.strptime(m.group(2), "%d/%m/%Y").date()
    s = next(
        (SUMMARY.match(ln.strip()) for ln in text.splitlines() if SUMMARY.match(ln.strip())), None
    )
    if s is None:
        raise ParseError(
            "Summary line (MOVIMIENTO saldo anterior, pagos, consumos, total) not found."
        )
    previous, credits, debits, due = (amount(s.group(i)) for i in range(1, 5))
    # The summary prints credits with a trailing "-": keep totals positive for the checks.
    totals = {
        "previous_balance": previous,
        "payments_credits": abs(credits),
        "purchases_debits": debits,
        "total_due": due,
    }
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=previous,
        closing_balance=due,
        totals=totals,
    )

    in_detail = False
    card: str | None = None
    person: str | None = None
    card_subtotals: dict[str, Decimal] = {}
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            if line == "DETALLE DE MOVIMIENTOS":
                in_detail = True
                continue
            if not in_detail or not line:
                continue
            if any(line.startswith(x) for x in DETAIL_END):
                if t := TOTAL_DUE.match(line):
                    totals["printed_total_due"] = amount(t.group(1))
                in_detail = False
                continue
            if p := PREVIOUS.match(line):
                totals["printed_previous"] = amount(p.group(1))
                continue
            if t := SUBTOTAL_PAYMENTS.match(line):
                totals["printed_payments"] = amount(t.group(1))
                continue
            if t := TOTAL_PURCHASES.match(line):
                totals["printed_purchases"] = amount(t.group(1))
                continue
            if t := SUBTOTAL_CARD.match(line):
                if card:
                    card_subtotals[card] = amount(t.group(1))
                continue
            if c := CARD.match(line):
                card = c.group("card")
                person = next(
                    (PEOPLE[w] for w in c.group("name").upper().split() if w in PEOPLE), None
                )
                continue
            if not (ln := LINE.match(line)):
                continue
            try:
                d = _date(ln.group("d"), start, end)
            except ValueError as exc:
                out.rejects.append(Reject(page_no, line_no, line, str(exc)))
                continue
            desc = ln.group("desc").strip()
            op = OPERATION.search(desc)
            if op:
                desc = desc[: op.start()].strip()
            value = amount(ln.group("amt"))
            out.lines.append(
                Line(
                    page=page_no,
                    line_no=line_no,
                    section=_section(desc, op.group("op") if op else None),
                    text=line,
                    txn_date=d,
                    post_date=None,
                    amount=-value,  # debits are money out; a credit ("310,00-") becomes positive
                    description=desc,
                    cardholder=card,
                    person=person,  # lines before the card blocks: the account owner
                    reference=ln.group("cuota"),
                )
            )
            if ln.group("dif"):
                totals[f"deferred_balance_{len(out.lines)}"] = amount(ln.group("dif"))

    _tie_out(out, card_subtotals)
    return out


def _tie_out(out: ParsedStatement, card_subtotals: dict[str, Decimal]) -> None:
    t = out.totals
    credits = sum((ln.amount for ln in out.lines if ln.amount > 0), Decimal(0))
    debits = -sum((ln.amount for ln in out.lines if ln.amount < 0), Decimal(0))
    out.checks += [
        Check("Payments and credits", t["payments_credits"], credits),
        Check("Purchases and charges", t["purchases_debits"], debits),
        Check(
            "Previous balance - payments + charges = total due",
            t["total_due"],
            t["previous_balance"] - credits + debits,
        ),
    ]
    for card, printed in sorted(card_subtotals.items()):
        lines = [ln for ln in out.lines if ln.cardholder == card]
        out.checks.append(
            Check(
                f"Card •••• {card} subtotal", printed, -sum((ln.amount for ln in lines), Decimal(0))
            )
        )
    if "printed_payments" in t:
        paid = sum((ln.amount for ln in out.lines if ln.section == "payment"), Decimal(0))
        out.checks.append(Check("Payments (SUBTOTAL PAGOS)", t["printed_payments"], paid))
    if "printed_purchases" in t:
        bought = -sum((ln.amount for ln in out.lines if ln.section == "purchase"), Decimal(0))
        out.checks.append(
            Check("Purchases this month (TOTAL CONSUMOS MES)", t["printed_purchases"], bought)
        )
    if "printed_total_due" in t:
        out.checks.append(
            Check("Total due printed in the detail", t["total_due"], t["printed_total_due"])
        )
    if "printed_previous" in t:
        out.checks.append(
            Check(
                "Previous balance printed in the detail",
                t["previous_balance"],
                t["printed_previous"],
            )
        )
