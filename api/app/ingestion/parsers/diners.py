"""Diners Club del Ecuador statements, in Spanish (F8). Hernan's and Lauren's share the layout.

Page 1 has the period ("04 JUN 2026 AL 03 JUL 2026") and the summary, one figure per line
("SALDO ANTERIOR: 708,82", "PAGOS/CRÉDITOS: 708,82-", "CONSUMOS: 439,81", "DÉBITOS: 0,00",
"Total a pagar: 439,81"). "Consumo período actual" lists purchases in one block per card
("NAME 0036-xxxx-xxxx-1234 * PRINCIPAL …") ending in "SUBTOTAL DE CONSUMOS: 439,81"; a deferred
purchase shows its installment and remaining balance ("10/11 1 COLEGIO … (8/12) 300,00
1.200,00"). "Compras con meses de gracia por facturar" lists purchases billed in a later
statement; they are skipped. "Detalle débitos y créditos" lists interest and charges ("03/08 INT.
FINANCIAMIENTO N/D 0,60") and payments ("16/06 11111 SU PAGO "MUCHAS GRACIAS" 708,82-") until
"TOTAL A PAGAR". Amounts use the Ecuadorian format. Layout notes in docs/parsers.md.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.ingestion.detect import ES_MONTHS, PEOPLE
from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    fold_accents,
    numbered_lines,
)
from app.ingestion.parsers.pichincha import amount

NAME = "diners"
NUM = r"\d{1,3}(?:\.\d{3})*,\d{2}-?"

PERIOD = re.compile(r"(\d{1,2}) ([A-Z]{3}) (\d{4}) AL (\d{1,2}) ([A-Z]{3}) (\d{4})")
SUMMARY = {
    "previous_balance": re.compile(rf"^SALDO ANTERIOR: ({NUM})", re.M),
    "payments_credits": re.compile(rf"^PAGOS/CREDITOS: ({NUM})", re.M),
    "purchases": re.compile(rf"^CONSUMOS: ({NUM})", re.M),
    "debits": re.compile(rf"^DEBITOS: ({NUM})", re.M),
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
    "printed_debits": re.compile(rf"^TOTAL DEBITOS: ({NUM})$"),
    "printed_credits": re.compile(rf"^TOTAL PAGOS Y CREDITOS: ({NUM})$"),
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


# The headings that start a block of the detail. A heading that maps to None starts a part that
# is skipped: purchases with grace months are billed (as installments) in a later statement, and
# "Consumo en el exterior" repeats foreign purchases already listed above.
BLOCKS = {
    "Consumo periodo actual": "purchases",
    "DETALLE DE DEBITOS": "debits",
    "DETALLE DE PAGOS Y CREDITOS": "credits",
    "Resumen consumos por cliente": "clients",
}
SKIPPED = ("Compras con meses de gracia", "Consumo en el exterior")
DATED = re.compile(r"^\d{2}/\d{2} ")
EARLIER = timedelta(days=7)  # how far before the period a date may be and still belong to it


def _period(text: str) -> tuple[date, date]:
    p = PERIOD.search(text)
    if not p:
        raise ParseError("Period (e.g. '04 JUN 2026 AL 03 JUL 2026') not found.")
    try:
        start = date(int(p.group(3)), ES_MONTHS[p.group(2).lower()], int(p.group(1)))
        end = date(int(p.group(6)), ES_MONTHS[p.group(5).lower()], int(p.group(4)))
    except (KeyError, ValueError) as exc:
        raise ParseError(f"Period could not be read: {p.group(0)}") from exc
    return start, end


def _summary(text: str) -> dict[str, Decimal]:
    """Page 1's figures; every one of them must be there."""
    totals: dict[str, Decimal] = {}
    for key, rx in SUMMARY.items():
        m = rx.search(text)
        if not m:
            raise ParseError(f"Summary figure '{rx.pattern.split(':')[0][1:]}' not found.")
        totals[key] = abs(amount(m.group(1)))
    return totals


class _TooManyAmounts(ValueError):
    """A purchase line with more amounts than its columns allow."""


@dataclass
class _Reader:
    """Reads the detail line by line, remembering the block and the card it is in. Each
    `_take_*` method says whether the line was its kind; `read` tries them in order."""

    out: ParsedStatement
    block: str | None = None  # purchases, debits, credits, clients
    card: str | None = None
    card_names: dict[str, str] = field(default_factory=dict)
    card_subtotals: dict[str, Decimal] = field(default_factory=dict)
    clients: dict[str, Decimal] = field(default_factory=dict)
    deferred: Decimal = Decimal(0)

    def read(self, page_no: int, line_no: int, line: str) -> None:
        """Read one line."""
        if self._take_block(line) or self.block is None:
            return
        if self._take_printed(line) or self._take_client(line) or self._take_card(line):
            return
        self._take_movement(page_no, line_no, line)

    def _take_block(self, line: str) -> bool:
        """A heading that starts a block of the detail, or a part that is skipped."""
        if line in BLOCKS:
            self.block = BLOCKS[line]
        elif line == "Detalle debitos y creditos":
            self.block = self.block if self.block in ("debits", "credits") else "debits"
        elif line.startswith(SKIPPED):
            self.block = None
        else:
            return False
        return True

    def _take_printed(self, line: str) -> bool:
        """A total the statement prints, kept for the checks."""
        if not _printed(line, self.out.totals, self.card, self.card_subtotals):
            return False
        if line.startswith(("TOTAL A PAGAR", "TOTAL CONSUMO POR CLIENTE")):
            self.block = None if self.block == "clients" else self.block
        return True

    def _take_client(self, line: str) -> bool:
        """Inside the summary by client, a client's total; nothing else there is a line."""
        if self.block != "clients":
            return False
        if c := CLIENT.match(line):
            self.clients[c.group("name")] = amount(c.group("amt"))
        return True

    def _take_card(self, line: str) -> bool:
        """The card a block of purchases belongs to."""
        if self.block != "purchases" or not (c := CARD.match(line)):
            return False
        self.card = c.group("card")
        self.card_names[self.card] = c.group("name").strip()
        return True

    def _purchase(self, m: re.Match[str], d: date) -> tuple[date, Decimal]:
        """A purchase's date and what it costs. Columns: CUOTA, VALOR, IVA, SALDO DIF. An
        installment line ends with its remaining balance ("(6/12) 336,00 2.016,00"); any number
        between is IVA. Otherwise a second number is IVA, part of the charge ("TARIFA CONSUMO
        GASOLINERA 0,20 0,03" costs 0,23; it was dropped, 2026-11-02)."""
        extra = [amount(x) for x in (m.group("x2"), m.group("x3")) if x]
        if m.group("cuota"):
            if d < self.out.period_start - EARLIER:
                d = self.out.period_end  # an earlier purchase
            if extra:
                self.deferred += extra.pop()
        elif len(extra) > 1:
            raise _TooManyAmounts("Too many amounts for a purchase")
        return d, amount(m.group("amt")) + sum(extra, Decimal(0))

    def _take_movement(self, page_no: int, line_no: int, line: str) -> None:
        """A dated line: a purchase, a charge or a payment, or a reject when it can't be read."""
        out, block = self.out, self.block
        assert block is not None
        purchase = block == "purchases"
        m = (PURCHASE if purchase else MOVEMENT).match(line)
        if not m:
            if DATED.match(line):
                out.rejects.append(Reject(page_no, line_no, line, "Line could not be read"))
            return
        try:
            d = _date(m.group("d"), out.period_end)
            d, value = self._purchase(m, d) if purchase else (d, amount(m.group("amt")))
        except ValueError as exc:
            out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            return
        desc = m.group("desc").strip()
        on_card = self.card if purchase else None
        out.lines.append(
            Line(
                page=page_no,
                line_no=line_no,
                section=_section(desc, block),
                text=line,
                txn_date=d,
                post_date=None,
                amount=-value,  # charges are money out; "708,82-" is in
                description=desc,
                cardholder=on_card,
                person=_person(self.card_names[on_card]) if on_card else None,
                reference=m.group("cuota") if purchase else None,
            )
        )


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Diners Club statement's pages (scans included): period, lines and checks."""
    pages = [fold_accents(p) for p in pages]  # OCR of a scan drops them: match without accents
    text = "\n".join(pages)
    start, end = _period(text)
    totals = _summary(text)
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=totals["previous_balance"],
        closing_balance=totals["total_due"],
        totals=totals,
    )
    reader = _Reader(out)
    for page_no, line_no, line in numbered_lines(pages):
        reader.read(page_no, line_no, line)
    _tie_out(out, reader.card_subtotals, reader.card_names, reader.clients, reader.deferred)
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
