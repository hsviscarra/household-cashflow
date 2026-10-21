"""Diners Club del Ecuador statements, in Spanish (F8). Hernan's and Lauren's share the layout.

Page 1 has the period ("04 JUN 2026 AL 03 JUL 2026") and the summary, one figure per line
("SALDO ANTERIOR: 708,82", "PAGOS/CRÉDITOS: 708,82-", "CONSUMOS: 439,81", "DÉBITOS: 0,00",
"Total a pagar: 439,81"). "Consumo período actual" lists purchases in one block per card
("NAME 0036-xxxx-xxxx-1234 * PRINCIPAL …") ending in "SUBTOTAL DE CONSUMOS: 439,81"; a deferred
purchase shows its installment and remaining balance ("10/11 1 COLEGIO … (8/12) 300,00
1.200,00"). "Detalle débitos y créditos" lists interest and charges ("03/08 INT. FINANCIAMIENTO
N/D 0,60") and payments ("16/06 11111 SU PAGO "MUCHAS GRACIAS" 708,82-") until "TOTAL A PAGAR".
Amounts use the Ecuadorian format. Layout notes in docs/parsers.md.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from app.ingestion.detect import ES_MONTHS, PEOPLE
from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError, Reject
from app.ingestion.parsers.pichincha import amount

NAME = "diners"
NUM = r"\d{1,3}(?:\.\d{3})*,\d{2}-?"

PERIOD = re.compile(r"(\d{1,2}) ([A-Z]{3}) (\d{4}) AL (\d{1,2}) ([A-Z]{3}) (\d{4})")
SUMMARY = {
    "previous_balance": re.compile(rf"^SALDO ANTERIOR: ({NUM})", re.M),
    "payments_credits": re.compile(rf"^PAGOS/CRÉDITOS: ({NUM})", re.M),
    "purchases": re.compile(rf"^CONSUMOS: ({NUM})", re.M),
    "debits": re.compile(rf"^DÉBITOS: ({NUM})", re.M),
    "total_due": re.compile(rf"^Total a pagar: ({NUM})", re.M | re.I),
}
CARD = re.compile(r"^(?P<name>.+?) \d{4}-x{4}-x{4}-(?P<card>\d{4})\b", re.I)
PURCHASE = re.compile(
    rf"^(?P<d>\d{{2}}/\d{{2}}) (?P<vale>\d+) (?P<desc>.+?)(?: \((?P<cuota>\d{{1,2}}/\d{{1,2}})\))? "
    rf"(?P<amt>{NUM})(?: (?P<x2>{NUM}))?(?: (?P<x3>{NUM}))?$"
)
MOVEMENT = re.compile(
    rf"^(?P<d>\d{{2}}/\d{{2}}) (?:\d+ )?(?P<desc>.+?)(?: N/[DC](?: T\d+)?)? (?P<amt>{NUM})$"
)
PRINTED = {
    "printed_card_subtotal": re.compile(rf"^SUBTOTAL DE CONSUMOS: ({NUM})$"),
    "printed_purchases": re.compile(rf"^TOTAL DE CONSUMOS: ({NUM})(?: ({NUM}))?$"),
    "printed_previous": re.compile(rf"^SALDO ANTERIOR ({NUM})$"),
    "printed_debits": re.compile(rf"^TOTAL DÉBITOS: ({NUM})$"),
    "printed_credits": re.compile(rf"^TOTAL PAGOS Y CRÉDITOS: ({NUM})$"),
    "printed_total_due": re.compile(rf"^TOTAL A PAGAR: ({NUM})$"),
    "printed_by_client": re.compile(rf"^TOTAL CONSUMO POR CLIENTE: ({NUM})$"),
}
CLIENT = re.compile(rf"^(?P<name>[A-ZÁÉÍÓÚÑ ]+?) (?P<amt>{NUM})$")


def _date(day_month: str, end: date) -> date:
    day, month = (int(x) for x in day_month.split("/"))
    d = date(end.year, month, day)
    return d if d <= end + timedelta(days=7) else date(end.year - 1, month, day)


def _section(desc: str, block: str) -> str:
    upper = desc.upper()
    if block == "purchases":
        return "purchase"
    if upper.startswith("SU PAGO"):
        return "payment"
    if upper.startswith(("INT. FINANCIAMIENTO", "INTERESES")):
        return "interest"
    if upper.startswith("GASTO GESTION COBRANZA"):
        return "fee"
    return "credit" if block == "credits" else "charge"  # SOLCA, IVA withheld, other N/D


def _person(name: str) -> str | None:
    return next((PEOPLE[w] for w in name.upper().split() if w in PEOPLE), None)


def parse(pages: list[str]) -> ParsedStatement:
    text = "\n".join(pages)
    p = PERIOD.search(text)
    if not p:
        raise ParseError("Period (e.g. '04 JUN 2026 AL 03 JUL 2026') not found.")
    try:
        start = date(int(p.group(3)), ES_MONTHS[p.group(2).lower()], int(p.group(1)))
        end = date(int(p.group(6)), ES_MONTHS[p.group(5).lower()], int(p.group(4)))
    except (KeyError, ValueError) as exc:
        raise ParseError(f"Period could not be read: {p.group(0)}") from exc
    totals: dict[str, Decimal] = {}
    for key, rx in SUMMARY.items():
        m = rx.search(text)
        if not m:
            raise ParseError(f"Summary figure '{rx.pattern.split(':')[0][1:]}' not found.")
        totals[key] = abs(amount(m.group(1)))
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=totals["previous_balance"],
        closing_balance=totals["total_due"],
        totals=totals,
    )

    block: str | None = None  # purchases, debits, credits, clients
    card: str | None = None
    card_names: dict[str, str] = {}
    card_subtotals: dict[str, Decimal] = {}
    clients: dict[str, Decimal] = {}
    deferred = Decimal(0)
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            if line == "Consumo período actual":
                block = "purchases"
                continue
            if line == "Detalle débitos y créditos":
                block = block if block in ("debits", "credits") else "debits"
                continue
            if line == "DETALLE DE DÉBITOS":
                block = "debits"
                continue
            if line == "DETALLE DE PAGOS Y CRÉDITOS":
                block = "credits"
                continue
            if line == "Resumen consumos por cliente":
                block = "clients"
                continue
            if line.startswith("Consumo en el exterior"):
                block = None  # repeats foreign purchases already listed above
                continue
            if block is None:
                continue
            if _printed(line, totals, card, card_subtotals):
                if line.startswith(("TOTAL A PAGAR", "TOTAL CONSUMO POR CLIENTE")):
                    block = None if block == "clients" else block
                continue
            if block == "clients":
                if c := CLIENT.match(line):
                    clients[c.group("name")] = amount(c.group("amt"))
                continue
            if block == "purchases" and (c := CARD.match(line)):
                card = c.group("card")
                card_names[card] = c.group("name").strip()
                continue
            rx = PURCHASE if block == "purchases" else MOVEMENT
            if not (m := rx.match(line)):
                if re.match(r"^\d{2}/\d{2} ", line):
                    out.rejects.append(Reject(page_no, line_no, line, "Line could not be read"))
                continue
            try:
                d = _date(m.group("d"), end)
            except ValueError as exc:
                out.rejects.append(Reject(page_no, line_no, line, str(exc)))
                continue
            cuota = m.group("cuota") if block == "purchases" else None
            if cuota:
                # An installment of an earlier purchase is billed in this period.
                d = end if d < start - timedelta(days=7) else d
                deferred += amount(m.group("x3") or m.group("x2") or "0,00")
            desc = m.group("desc").strip()
            on_card = card if block == "purchases" else None
            out.lines.append(
                Line(
                    page=page_no,
                    line_no=line_no,
                    section=_section(desc, block),
                    text=line,
                    txn_date=d,
                    post_date=None,
                    amount=-amount(m.group("amt")),  # charges are money out; "708,82-" is in
                    description=desc,
                    cardholder=on_card,
                    person=_person(card_names[on_card]) if on_card else None,
                    reference=cuota,
                )
            )

    _tie_out(out, card_subtotals, card_names, clients, deferred)
    return out


def _printed(
    line: str, totals: dict[str, Decimal], card: str | None, card_subtotals: dict[str, Decimal]
) -> bool:
    for key, rx in PRINTED.items():
        if m := rx.match(line):
            value = abs(amount(m.group(1)))
            if key == "printed_card_subtotal":
                if card:
                    card_subtotals[card] = value
            else:
                totals[key] = value
            if key == "printed_purchases" and m.group(2):
                totals["printed_deferred"] = amount(m.group(2))
            return True
    return False


def _tie_out(
    out: ParsedStatement,
    card_subtotals: dict[str, Decimal],
    card_names: dict[str, str],
    clients: dict[str, Decimal],
    deferred: Decimal,
) -> None:
    t = out.totals

    def spent(lines: list[Line]) -> Decimal:
        return -sum((ln.amount for ln in lines), Decimal(0))

    purchases = spent([ln for ln in out.lines if ln.section == "purchase"])
    others = [ln for ln in out.lines if ln.section != "purchase"]
    credits = sum((ln.amount for ln in others if ln.amount > 0), Decimal(0))
    debits = spent([ln for ln in others if ln.amount < 0])
    out.checks += [
        Check("Purchases (CONSUMOS)", t["purchases"], purchases),
        Check("Interest and charges (DÉBITOS)", t["debits"], debits),
        Check("Payments and credits", t["payments_credits"], credits),
        Check(
            "Previous balance - payments + purchases + charges = total due",
            t["total_due"],
            t["previous_balance"] - credits + purchases + debits,
        ),
    ]
    for card, printed in sorted(card_subtotals.items()):
        on_card = [ln for ln in out.lines if ln.cardholder == card]
        out.checks.append(Check(f"Card •••• {card} subtotal", printed, spent(on_card)))
    for name, printed in sorted(clients.items()):
        cards = {c for c, n in card_names.items() if n == name}
        mine = [ln for ln in out.lines if ln.cardholder in cards]
        label = (_person(name) or "Cardholder") + "'s purchases (Resumen por cliente)"
        out.checks.append(Check(label, printed, spent(mine)))
    printed_checks = [
        ("printed_purchases", "Purchases printed in the detail", t["purchases"]),
        ("printed_debits", "Charges printed in the detail", t["debits"]),
        ("printed_credits", "Payments printed in the detail", t["payments_credits"]),
        ("printed_total_due", "Total due printed in the detail", t["total_due"]),
        ("printed_previous", "Previous balance printed in the detail", t["previous_balance"]),
    ]
    for key, label, expected in printed_checks:
        if key in t:
            out.checks.append(Check(label, expected, t[key]))
    if "printed_deferred" in t:
        out.checks.append(
            Check("Remaining balance of deferred purchases", t["printed_deferred"], deferred)
        )
