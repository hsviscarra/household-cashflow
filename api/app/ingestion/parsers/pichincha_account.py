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
from datetime import date, timedelta
from decimal import Decimal

from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    fold_accents,
)

NAME = "pichincha"
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
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


def parse(pages: list[str]) -> ParsedStatement:
    text = fold_accents("\n".join(pages)).upper()
    last, this = LAST_CUT.search(text), THIS_CUT.search(text)
    if not this:
        raise ParseError("Period (FECHA ESTE CORTE) not found.")
    end = _dmy(*this.groups())
    start = _dmy(*last.groups()) + timedelta(days=1) if last else end.replace(day=1)
    o, c = OPENING.search(text), CLOSING.search(text)
    if not o or not c:
        raise ParseError("Opening or closing balance (SALDO ANTERIOR / SALDO ACTUAL) not found.")
    opening, closing = _num(o.group(1)), _num(c.group(1))
    cr, db = CREDITS.search(text), DEBITS.search(text)
    totals = {"opening": opening, "closing": closing}
    if cr:
        totals["credits"] = _num(cr.group(2))
    if db:
        totals["debits"] = _num(db.group(2))
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=opening,
        closing_balance=closing,
        totals=totals,
    )

    running, gaps = opening, Decimal(0)
    credits = debits = Decimal(0)
    n_credits = n_debits = 0
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            m = LINE.match(line)
            if not m:
                if LOOKS_LIKE_LINE.search(line):
                    out.rejects.append(Reject(page_no, line_no, line, "Line could not be read"))
                continue
            month = MONTHS.get(m.group("mon").lower())
            if month is None:
                out.rejects.append(Reject(page_no, line_no, line, "Unknown month"))
                continue
            year = end.year if month <= end.month else end.year - 1
            try:
                d = date(year, month, int(m.group("day")))
            except ValueError as exc:
                out.rejects.append(Reject(page_no, line_no, line, str(exc)))
                continue
            debit, credit = _num(m.group("debit")), _num(m.group("credit"))
            if debit:
                debits += debit
                n_debits += 1
            if credit:
                credits += credit
                n_credits += 1
            amount = credit - debit
            running += amount
            printed = _num(m.group("balance"))
            gaps += abs(printed - running)
            running = printed  # resynchronize so one misprint is counted at most twice
            desc = m.group("desc").strip()
            out.lines.append(Line(page_no, line_no, _section(desc), line, d, None, amount, desc))

    moved = sum((ln.amount for ln in out.lines), Decimal(0))
    out.checks += [
        Check("Opening balance + lines = closing balance", closing, opening + moved),
        Check("Gaps in the running balance, line by line", Decimal(0), gaps),
    ]
    if cr:
        out.checks += [
            Check("Credits add up to the summary", totals["credits"], credits),
            Check("Number of credits", Decimal(cr.group(1)), Decimal(n_credits)),
        ]
    if db:
        out.checks += [
            Check("Debits add up to the summary", totals["debits"], debits),
            Check("Number of debits", Decimal(db.group(1)), Decimal(n_debits)),
        ]
    return out
