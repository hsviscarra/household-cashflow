"""Banco Pichincha bank account statements, in Spanish (F19). Same source as the card
("pichincha"); app.ingestion.parsers.pichincha hands these over when the summary has
"CHEQUES / DÉBITOS".

Page 1: "FECHA ÚLTIMO CORTE (FACTURA) 07-08-2026" and "FECHA ESTE CORTE 04-09-2026" (the period
runs from the day after the last cut to this one), "SALDO ANTERIOR 40.00", "DEPÓSITO / CRÉDITOS (2)
1100.00", "CHEQUES / DÉBITOS (3) 50.41", "SALDO ACTUAL 1089.59". Then "DETALLE DE MOVIMIENTOS",
one line per movement with the running balance:
"18-ago. 12 1002 TRANSFERENCIA INTERBANCARIA RECIBIDA 0.00 100.00 90.00"
(day-month, branch, document number, description, debit, credit, balance). Amounts use the US
format. Layout notes in docs/parsers.md.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
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

NAME = "pichincha"
# Spanish ("18-ago.") and, in some statements (January 2026), English ("09-Dec", "05-Jan"): only
# Jan, Apr, Aug and Dec differ.
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}  # fmt: skip
AMT = r"-?[\d,]*\d\.\d{2}"
DMY = r"(\d{2})-(\d{2})-(\d{4})"

LAST_CUT = re.compile(rf"FECHA ULTIMO CORTE(?: \(FACTURA\))? {DMY}")
THIS_CUT = re.compile(rf"FECHA ESTE CORTE(?: \(FACTURA\))? {DMY}")
OPENING = re.compile(rf"SALDO ANTERIOR ({AMT})")
CLOSING = re.compile(rf"SALDO ACTUAL ({AMT})")
CREDITS = re.compile(rf"DEPOSITO / CREDITOS \((\d+)\) ({AMT})")
DEBITS = re.compile(rf"CHEQUES / DEBITOS \((\d+)\) ({AMT})")
LINE = re.compile(
    rf"^(?P<day>\d{{1,2}})-(?P<mon>[a-z]{{3}})\.? (?P<branch>\d+) (?P<doc>\d+) (?P<desc>.+?) "
    rf"(?P<debit>{AMT}) (?P<credit>{AMT}) (?P<balance>{AMT})$",
    re.IGNORECASE,
)
LOOKS_LIKE_LINE = re.compile(rf" {AMT} {AMT} {AMT}$")


def is_account_statement(text: str) -> bool:
    """Whether the text is Pichincha's bank account statement, not its card's."""
    return "CHEQUES / DEBITOS" in fold_accents(text).upper()


def _num(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _dmy(d: str, m: str, y: str) -> date:
    return date(int(y), int(m), int(d))


def _section(desc: str) -> str:
    upper = fold_accents(desc).upper().lstrip("*")
    if upper.startswith(("COMISION", "IVA COBRADO", "TARIFA")):
        return "fee"
    if upper.startswith("INTERES"):
        return "interest_earned"
    return "movement"


Printed = tuple[int, Decimal]  # how many movements the summary counts, and what they add up to


@dataclass(frozen=True)
class _Header:
    """Page 1: the period between the two cuts, the balances, and the summary's credits and
    debits when it prints them."""

    start: date
    end: date
    opening: Decimal
    closing: Decimal
    credits: Printed | None
    debits: Printed | None


def _printed(m: re.Match[str] | None) -> Printed | None:
    return (int(m.group(1)), _num(m.group(2))) if m else None


def _header(text: str) -> _Header:
    last, this = LAST_CUT.search(text), THIS_CUT.search(text)
    if not this:
        raise ParseError("Period (FECHA ESTE CORTE) not found.")
    end = _dmy(*this.groups())
    start = _dmy(*last.groups()) + timedelta(days=1) if last else end.replace(day=1)
    o, c = OPENING.search(text), CLOSING.search(text)
    if not o or not c:
        raise ParseError("Opening or closing balance (SALDO ANTERIOR / SALDO ACTUAL) not found.")
    return _Header(
        start,
        end,
        _num(o.group(1)),
        _num(c.group(1)),
        _printed(CREDITS.search(text)),
        _printed(DEBITS.search(text)),
    )


@dataclass
class _Tally:
    """What the lines add up to as they are read, and how far the printed running balance
    strays from it."""

    running: Decimal
    gaps: Decimal = Decimal(0)
    credits: Decimal = Decimal(0)
    debits: Decimal = Decimal(0)
    n_credits: int = 0
    n_debits: int = 0

    def add(self, debit: Decimal, credit: Decimal, printed: Decimal) -> None:
        """Count one line against the balance printed beside it."""
        if debit:
            self.debits += debit
            self.n_debits += 1
        if credit:
            self.credits += credit
            self.n_credits += 1
        self.running += credit - debit
        self.gaps += abs(printed - self.running)
        self.running = printed  # resynchronize so one misprint is counted at most twice


def _line_date(m: re.Match[str], end: date) -> date:
    """A line's date: its month is in the cut's year, or the year before when it is later than
    the cut's month. ValueError when it can't be a date."""
    month = MONTHS.get(m.group("mon").lower())
    if month is None:
        raise ValueError("Unknown month")
    year = end.year if month <= end.month else end.year - 1
    return date(year, month, int(m.group("day")))


def _checks(h: _Header, tally: _Tally, lines: list[Line]) -> list[Check]:
    moved = sum((ln.amount for ln in lines), Decimal(0))
    checks = [
        Check("Opening balance + lines = closing balance", h.closing, h.opening + moved),
        Check("Gaps in the running balance, line by line", Decimal(0), tally.gaps),
    ]
    if h.credits:
        checks += [
            Check("Credits add up to the summary", h.credits[1], tally.credits),
            Check("Number of credits", Decimal(h.credits[0]), Decimal(tally.n_credits)),
        ]
    if h.debits:
        checks += [
            Check("Debits add up to the summary", h.debits[1], tally.debits),
            Check("Number of debits", Decimal(h.debits[0]), Decimal(tally.n_debits)),
        ]
    return checks


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Banco Pichincha account statement's pages: cut dates, balances, lines and checks."""
    h = _header(fold_accents("\n".join(pages)).upper())
    totals = {"opening": h.opening, "closing": h.closing}
    if h.credits:
        totals["credits"] = h.credits[1]
    if h.debits:
        totals["debits"] = h.debits[1]
    out = ParsedStatement(
        parser=NAME,
        period_start=h.start,
        period_end=h.end,
        opening_balance=h.opening,
        closing_balance=h.closing,
        totals=totals,
    )
    tally = _Tally(h.opening)
    for page_no, line_no, line in numbered_lines(pages):
        m = LINE.match(line)
        if not m:
            if LOOKS_LIKE_LINE.search(line):
                out.rejects.append(Reject(page_no, line_no, line, "Line could not be read"))
            continue
        try:
            d = _line_date(m, h.end)
        except ValueError as exc:
            out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            continue
        debit, credit = _num(m.group("debit")), _num(m.group("credit"))
        tally.add(debit, credit, _num(m.group("balance")))
        desc = m.group("desc").strip()
        out.lines.append(
            Line(page_no, line_no, _section(desc), line, d, None, credit - debit, desc)
        )
    out.checks += _checks(h, tally, out.lines)
    return out
