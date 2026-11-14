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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.ingestion.parsers import pichincha_account
from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    numbered_lines,
)

NAME = "pichincha"
NUM = r"[\d.,]+[.,]\d{2}-?"

PERIOD = re.compile(r"(\d{2}/\d{2}/\d{4}) (\d{2}/\d{2}/\d{4})")
# "MOVIMIENTO 527.69 1,057.81- …" (2026 from July) or "MOVIMIENTOS 44,59 70,00- 25,41 0,00"
# (earlier months, Ecuadorian amounts).
SUMMARY = re.compile(rf"^MOVIMIENTOS? ({NUM}) ({NUM}) ({NUM}) ({NUM})$")
CARD = re.compile(r"^(?P<name>[A-ZÁÉÍÓÚÑ ]+?) \d{4}-x{4}-x{4}-(?P<card>\d{4})\b", re.IGNORECASE)
LINE = re.compile(
    rf"^(?P<d>\d{{2}}/\d{{2}}) (?:(?P<ref>\d{{3,}}) )?(?P<desc>.+?) "
    rf"(?:(?P<cuota>\d{{1,2}}/\d{{1,2}}) )?(?P<amt>{NUM})(?: (?P<dif>{NUM}))?$"
)
# From mid-2026 an installment reads "05/01 978746 PTP - BMI … DIFERIDO (6/12) 71,04 426,24": the
# purchase's own date (January), installment 6 of 12, then the deferred balance.
# The last one reads "DIFERIDO (FINAL)" (April 2026), with no plan length: up to the longest plan.
INSTALLMENT = re.compile(r" DIFERIDO \((?:(?P<n>\d{1,2})/(?P<of>\d{1,2})|(?P<final>FINAL))\)$")
LONGEST_PLAN = 36  # months, the longest deferral the card offers
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


def _bought_within(day_month: str, end: date, months: int) -> bool:
    """An installment's purchase date: at most the plan's length (plus a month) before the end."""
    for year in (end.year, end.year - 1, end.year - 2):
        try:
            d = datetime.strptime(f"{day_month}/{year}", "%d/%m/%Y").date()
        except ValueError:
            return False
        if end - timedelta(days=31 * (months + 1)) <= d <= end:
            return True
    return False


def _section(desc: str, op: str | None) -> str:
    upper = desc.upper()
    if upper.startswith("SU PAGO"):
        return "payment"
    if "INT. FINANCIAMIENTO" in upper or upper.startswith("INTERESES"):
        return "interest"
    if op == "CONSUMO":
        return "purchase"
    return "charge"  # SOLCA, RET IVA, early payoffs and other N/D / N/C lines


# Totals printed inside the detail, kept for the checks: where each goes in `totals`.
PRINTED = {
    "printed_previous": PREVIOUS,
    "printed_payments": SUBTOTAL_PAYMENTS,
    "printed_purchases": TOTAL_PURCHASES,
}


def _period(text: str) -> tuple[date, date]:
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Period (PERÍODO DESDE … HASTA) not found.")
    return (
        datetime.strptime(m.group(1), "%d/%m/%Y").date(),
        datetime.strptime(m.group(2), "%d/%m/%Y").date(),
    )


def _summary(text: str) -> dict[str, Decimal]:
    """The summary line's four amounts: previous balance, payments, purchases, total due."""
    s = next(
        (SUMMARY.match(ln.strip()) for ln in text.splitlines() if SUMMARY.match(ln.strip())), None
    )
    if s is None:
        raise ParseError(
            "Summary line (MOVIMIENTO saldo anterior, pagos, consumos, total) not found."
        )
    previous, credits, debits, due = (amount(s.group(i)) for i in range(1, 5))
    # The summary prints credits with a trailing "-": keep totals positive for the checks.
    return {
        "previous_balance": previous,
        "payments_credits": abs(credits),
        "purchases_debits": debits,
        "total_due": due,
    }


@dataclass
class _Reader:
    """Reads "DETALLE DE MOVIMIENTOS" line by line, remembering whose card block it is in. Each
    `_take_*` method says whether the line was its kind; `read` tries them in order."""

    out: ParsedStatement
    in_detail: bool = False
    card: str | None = None
    person: str | None = None
    card_subtotals: dict[str, Decimal] = field(default_factory=dict)

    def read(self, page_no: int, line_no: int, line: str) -> None:
        """Read one line."""
        if line == "DETALLE DE MOVIMIENTOS":
            self.in_detail = True
            return
        if not self.in_detail or not line:
            return
        if self._take_end(line) or self._take_printed(line) or self._take_card(line):
            return
        self._take_movement(page_no, line_no, line)

    def _take_end(self, line: str) -> bool:
        """The line that closes the detail (it may print the total due)."""
        if not any(line.startswith(x) for x in DETAIL_END):
            return False
        if t := TOTAL_DUE.match(line):
            self.out.totals["printed_total_due"] = amount(t.group(1))
        self.in_detail = False
        return True

    def _take_printed(self, line: str) -> bool:
        """A total the detail prints, or a card's subtotal."""
        for key, rx in PRINTED.items():
            if t := rx.match(line):
                self.out.totals[key] = amount(t.group(1))
                return True
        if t := SUBTOTAL_CARD.match(line):
            if self.card:
                self.card_subtotals[self.card] = amount(t.group(1))
            return True
        return False

    def _take_card(self, line: str) -> bool:
        """The heading of a card's block."""
        c = CARD.match(line)
        if not c:
            return False
        self.card = c.group("card")
        self.person = next(
            (PEOPLE[w] for w in c.group("name").upper().split() if w in PEOPLE), None
        )
        return True

    def _when(self, day_month: str, inst: re.Match[str] | None) -> date:
        """A line's date. An installment prints its purchase's own date, which may be long
        before the period: it is billed on this statement's cut-off. ValueError otherwise."""
        out = self.out
        try:
            return _date(day_month, out.period_start, out.period_end)
        except ValueError:
            if inst is None:
                raise
            plan = LONGEST_PLAN if inst.group("final") else int(inst.group("of"))
            if not _bought_within(day_month, out.period_end, plan):
                raise
            return out.period_end

    def _take_movement(self, page_no: int, line_no: int, line: str) -> None:
        """A dated line: a purchase, payment or charge, or a reject when its date is off."""
        ln = LINE.match(line)
        if not ln:
            return
        out = self.out
        desc = ln.group("desc").strip()
        cuota = ln.group("cuota")
        inst = INSTALLMENT.search(desc)
        if inst:
            cuota = inst.group("final") or f"{inst.group('n')}/{inst.group('of')}"
            desc = desc[: inst.start()] + " DIFERIDO"
        try:
            d = self._when(ln.group("d"), inst)
        except ValueError as exc:
            out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            return
        op = OPERATION.search(desc)
        if op:
            desc = desc[: op.start()].strip()
        out.lines.append(
            Line(
                page=page_no,
                line_no=line_no,
                section=_section(desc, "CONSUMO" if inst else op.group("op") if op else None),
                text=line,
                txn_date=d,
                post_date=None,
                # Debits are money out; a credit ("310,00-") becomes positive.
                amount=-amount(ln.group("amt")),
                description=desc,
                cardholder=self.card,
                person=self.person,  # lines before the card blocks: the account owner
                reference=cuota,
            )
        )
        if ln.group("dif"):
            out.totals[f"deferred_balance_{len(out.lines)}"] = amount(ln.group("dif"))


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Banco Pichincha statement: the card, or the bank account when the pages are one."""
    text = "\n".join(pages)
    if pichincha_account.is_account_statement(text):  # the bank account, not the card (F19)
        return pichincha_account.parse(pages)
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
    _tie_out(out, reader.card_subtotals)
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
