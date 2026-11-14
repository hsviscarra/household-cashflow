"""Produbanco credit card statements (Visa), Hernan's card ending 5997.

Page 1 has "TARJETA No.:400929XXXXXX5997", "Periodo : 07/01/2026 - 07/31/2026" (month first) and
the summary "US$ 40.24 US$ 40.24 US$ 129.94 US$ 129.94" (saldo anterior, pagos/créditos,
consumos/débitos, total a pagar). "Detalle de movimientos del período" lists, per card, its
purchases ("07/01/2026 123 MEGADATOS S A EC 840 CONS. 40.24 +"), then the account's charges
("N/D(*)", taxed with IVA) and payments ("PAGO 40.24 -"), each block closed by a total:
TOTAL MONTO UTILIZADO, TOTAL CARGOS, TOTAL PAGOS Y CRÉDITOS, then PAGO TOTAL. "+" adds to the
debt, "-" pays it down. A foreign purchase may print its foreign amount and exchange rate before
the dollar amount; the dollar amount (Valor M.L.) is the last one. Layout notes in docs/parsers.md.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    fold_accents,
    numbered_lines,
)

NAME = "produbanco"  # one source with the savings statements; the reader tells them apart
AMT = r"-?[\d,]*\d\.\d{2}"

PERIOD = re.compile(r"Periodo\s*:\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2})/(\d{2})/(\d{4})")
SUMMARY = re.compile(rf"^US\$ ({AMT}) US\$ ({AMT}) US\$ ({AMT}) US\$ ({AMT})$")
LINE = re.compile(rf"^(?P<d>\d{{2}}/\d{{2}}/\d{{4}}) (?P<rest>.+) (?P<amt>{AMT}) (?P<sign>[+-])$")
DATED = re.compile(r"^\d{2}/\d{2}/\d{4} ")
OPERATION = re.compile(r" (?P<op>CONS\.?|N/D(?:\(\*\))?|N/C(?:\(\*\))?|PAGO|DIF\.?|INT\.?)$")
# A foreign amount or an exchange rate before the dollar amount; from October 2026 the foreign
# amount carries its own sign ("CONS. 2.92 + 1.0000 2.92 +").
NUMBER = re.compile(r" [\d,]*\d\.\d{2,6}(?: [+-])?$")
COUNTRY = re.compile(r" [A-Z]{2} \d{3}$")  # "EC 840": country and currency code of a purchase
HOLDER = re.compile(r"^\d{4}X{4,}\d{3,4} (?P<name>[A-ZÁÉÍÓÚÑ ]{5,})$")
TOTALS = {
    "purchases": re.compile(rf"^TOTAL MONTO UTILIZADO ({AMT})$"),
    "charges": re.compile(rf"^TOTAL CARGOS ({AMT})$"),
    "payments": re.compile(rf"^TOTAL PAGOS Y CREDITOS ({AMT}) ?-?$"),
    "printed_total": re.compile(rf"^PAGO TOTAL ({AMT})$"),
}
GROUPS = {"CONS": "purchases", "DIF": "purchases", "N/D": "charges", "INT": "charges"}
GROUPS |= {"PAGO": "payments", "N/C": "payments"}
PEOPLE = {"HERNAN": "Hernan", "LAUREN": "Lauren"}
LABELS = {
    "purchases": "Purchases (TOTAL MONTO UTILIZADO)",
    "charges": "Charges (TOTAL CARGOS)",
    "payments": "Payments and credits (TOTAL PAGOS Y CRÉDITOS)",
}


def is_card_statement(text: str) -> bool:
    """Whether the text is Produbanco's Visa card statement, not the savings account's."""
    return "TARJETA No.:" in text and "Resumen de movimientos" in text


def _num(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _mdy(m: str, d: str, y: str) -> date:
    return date(int(y), int(m), int(d))


def _section(op: str, desc: str) -> str:
    upper = desc.upper()
    if op == "PAGO":
        return "payment"
    if op == "N/C":
        return "credit"
    if op == "INT" or upper.startswith("INTERES"):
        return "interest"
    if op == "N/D" and ("TARIFA" in upper or "PREMIOS" in upper or "COMISION" in upper):
        return "fee"  # yearly card fees and the rewards program, taxed with IVA
    if op == "N/D":
        return "charge"
    return "purchase"


DETAIL_START = "Detalle de movimientos del periodo"
# Operations printed with "-": the payments group counts them as positive.
REDUCE_DEBT = ("PAGO", "N/C")


def _header(text: str) -> tuple[date, date, dict[str, Decimal]]:
    """The period, and the summary's four amounts: previous balance, payments, purchases, due."""
    p = PERIOD.search(text)
    if not p:
        raise ParseError("Period (Periodo : MM/DD/YYYY - MM/DD/YYYY) not found.")
    start, end = _mdy(*p.group(1, 2, 3)), _mdy(*p.group(4, 5, 6))
    summary = next((m for ln in text.splitlines() if (m := SUMMARY.match(ln.strip()))), None)
    if summary is None:
        raise ParseError("Summary (Saldo anterior, Pagos/Créditos, Consumos/Débitos) not found.")
    previous, credits, debits, due = (_num(summary.group(i)) for i in range(1, 5))
    return (
        start,
        end,
        {
            "previous_balance": previous,
            "payments_credits": credits,
            "purchases_debits": debits,
            "total_due": due,
        },
    )


def _movement(line: str) -> tuple[re.Match[str], str, str]:
    """A dated line's match, its operation and its description. ValueError, with the reason,
    when the amount or the operation can't be read."""
    m = LINE.match(line)
    if not m:
        raise ValueError("amount or sign not readable")
    rest = m.group("rest")
    while NUMBER.search(rest):  # foreign amount and rate before the dollar amount
        rest = NUMBER.sub("", rest)
    op = OPERATION.search(rest)
    if not op:
        raise ValueError("operation not recognized")
    words = rest[: op.start()].split()
    if words and words[0].isdigit():
        words = words[1:]  # the voucher reference
    desc = COUNTRY.sub("", " ".join(words)).strip()
    return m, re.sub(r"[^A-Z/]", "", op.group("op")), desc


@dataclass
class _Reader:
    """Reads the period's detail line by line, remembering whose block it is in and what each
    group of operations moved."""

    out: ParsedStatement
    moved: dict[str, Decimal] = field(
        default_factory=lambda: {
            "purchases": Decimal(0),
            "charges": Decimal(0),
            "payments": Decimal(0),
        }
    )
    in_detail: bool = False
    person: str | None = None

    def read(self, page_no: int, line_no: int, line: str) -> None:
        """Read one line."""
        if fold_accents(line).startswith(DETAIL_START):
            self.in_detail = True
            return
        if not self.in_detail or not line:
            return
        if self._take_total(line) or self._take_holder(line):
            return
        if DATED.match(line) and "SALDO ANTERIOR" not in line:
            self._take_movement(page_no, line_no, line)

    def _take_total(self, line: str) -> bool:
        """A total the detail prints; PAGO TOTAL closes the detail."""
        folded = fold_accents(line)
        hit = next(((k, m) for k, rx in TOTALS.items() if (m := rx.match(folded))), None)
        if not hit:
            return False
        self.out.totals[hit[0]] = _num(hit[1].group(1))
        if hit[0] == "printed_total":
            self.in_detail = False
        return True

    def _take_holder(self, line: str) -> bool:
        """The heading of a cardholder's block."""
        h = HOLDER.match(line)
        if not h:
            return False
        words = h.group("name").upper().split()
        self.person = next((PEOPLE[w] for w in words if w in PEOPLE), None)
        return True

    def _take_movement(self, page_no: int, line_no: int, line: str) -> None:
        """A dated line: a movement, or a reject when it can't be read."""
        try:
            m, kind, desc = _movement(line)
        except ValueError as exc:
            self.out.rejects.append(
                Reject(page_no, line_no, line, f"Line could not be read: {exc}")
            )
            return
        value = _num(m.group("amt")) * (1 if m.group("sign") == "+" else -1)
        self.moved[GROUPS[kind]] += value if kind not in REDUCE_DEBT else -value
        self.out.lines.append(
            Line(
                page=page_no,
                line_no=line_no,
                section=_section(kind, desc),
                text=line,
                txn_date=_mdy(*m.group("d").split("/")),
                post_date=None,
                amount=-value,  # "+" adds to the debt: money out
                description=desc,
                person=self.person,
            )
        )


def _checks(totals: dict[str, Decimal], moved: dict[str, Decimal]) -> list[Check]:
    previous, credits = totals["previous_balance"], totals["payments_credits"]
    debits, due = totals["purchases_debits"], totals["total_due"]
    checks = [
        Check(label, totals[key], moved[key]) for key, label in LABELS.items() if key in totals
    ]
    checks += [
        Check(
            "Purchases and charges (Consumos/Débitos)",
            debits,
            moved["purchases"] + moved["charges"],
        ),
        Check("Payments and credits (Pagos/Créditos)", credits, moved["payments"]),
        Check(
            "Previous balance - payments + purchases and charges = total due",
            due,
            previous - moved["payments"] + moved["purchases"] + moved["charges"],
        ),
    ]
    if "printed_total" in totals:
        checks.append(Check("Total due printed in the detail", due, totals["printed_total"]))
    return checks


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Produbanco Visa statement's pages: period, lines and checks."""
    start, end, totals = _header("\n".join(pages))
    out = ParsedStatement(
        parser="produbanco_card",
        period_start=start,
        period_end=end,
        opening_balance=totals["previous_balance"],
        closing_balance=totals["total_due"],
        totals=totals,
    )
    reader = _Reader(out)
    for page_no, line_no, line in numbered_lines(pages):
        reader.read(page_no, line_no, line)
    out.checks += _checks(totals, reader.moved)
    return out
