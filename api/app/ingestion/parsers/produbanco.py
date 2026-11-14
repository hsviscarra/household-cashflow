"""Produbanco savings account statements ("Estado Digital de Cuenta"), Hernan's and Lauren's (F7).

"Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026", "Saldo inicial contable: 297.71", "Saldo final
contable: 6.73", then one line per movement with the running balance:
"Quito Jul 8 100000000004 PAGO IESS BANCA EN LINEA -100.00 1,849.59 1,849.59"
(city, day, number, description, amount, book balance, available balance). Month names are
Spanish in the lines (Ago, Dic, ...) and English in the period; a "#" before the description marks
a fee that carries IVA. Layout notes in docs/parsers.md.
"""

import re
from datetime import date
from decimal import Decimal

from app.ingestion.parsers import produbanco_card
from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    numbered_lines,
)

NAME = "produbanco"
MONTHS = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "aug": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12,
}  # fmt: skip
MON = "|".join(m.capitalize() for m in MONTHS)
AMT = r"[+-]?[\d,]*\d\.\d{2}"

PERIOD = re.compile(rf"Del (\d{{1,2}}) ({MON}) (\d{{4}}) Al (\d{{1,2}}) ({MON}) (\d{{4}})", re.I)
OPENING = re.compile(rf"Saldo inicial contable: ({AMT})")
CLOSING = re.compile(rf"Saldo final contable: ({AMT})")
LINE = re.compile(
    rf"^(?P<city>.+?) (?P<mon>{MON}) (?P<day>\d{{1,2}}) (?P<num>\S+) (?:# )?(?P<desc>.+?) "
    rf"(?P<amt>[+-]?[\d,]*\d\.\d{{2}}) (?P<bal>{AMT}) (?P<avail>{AMT})$",
    re.I,
)
LOOKS_LIKE_LINE = re.compile(rf" [+-]?[\d,]*\d\.\d{{2}} {AMT} {AMT}$")


def _section(desc: str) -> str:
    upper = desc.upper()
    if upper.startswith(("TARIFA", "COMISION", "IVA ")):
        return "fee"
    if upper.startswith("PAGO TARJETA CREDITO"):
        return "payment"
    if upper.startswith("CAPITALIZACION DE INTERESES"):
        return "interest_earned"
    return "movement"


def _num(text: str) -> Decimal:
    return Decimal(text.replace(",", "").replace("+", ""))


def _period_date(day: str, mon: str, year: str) -> date:
    return date(int(year), MONTHS[mon[:3].lower()], int(day))


MAX_STEPS = 20_000  # the search below; a statement has a few dozen lines


Found = tuple[Line, str, Decimal]  # the line, its amount as printed, the balance after it
Step = tuple[int, int]  # a line's index, and 1 or -1 (-1: the amount's sign was lost)


def _sign_lost(raw_amount: str) -> bool:
    """Whether an amount printed without its sign (an OCR read) could be money out."""
    return raw_amount[0] not in "+-"


def _options(found: list[Found], used: list[bool], running: Decimal) -> list[Step]:
    """The unused lines whose balance follows `running`, earlier dates and text order first."""
    out = []
    for k, (ln, raw_amt, bal) in sorted(enumerate(found), key=lambda e: (e[1][0].txn_date, e[0])):
        if used[k]:
            continue
        if running + ln.amount == bal:
            out.append((k, 1))
        elif _sign_lost(raw_amt) and running - ln.amount == bal:
            out.append((k, -1))
    return out


def _chain(found: list[Found], opening: Decimal) -> list[Step] | None:
    """An order of all lines in which each one's balance is the previous balance plus its amount,
    as (index, sign) pairs; sign -1 means the amount's sign was lost (an OCR read) and the balance
    shows the money went out. Earlier dates and text order are tried first; a dead end steps back
    (a balance can repeat, e.g. -2,000 and +2,000 on one day). None when no order fits."""
    n = len(found)
    used = [False] * n
    path: list[Step] = []
    stack = [_options(found, used, opening)]
    for _ in range(MAX_STEPS):
        if not stack:
            break
        if len(path) == n:
            return path
        if not stack[-1]:
            stack.pop()
            if path:
                k, _sign = path.pop()
                used[k] = False
            continue
        k, sign = stack[-1].pop(0)
        used[k] = True
        path.append((k, sign))
        stack.append(_options(found, used, found[k][2]))
    return None


def _header(text: str) -> tuple[date, date, Decimal, Decimal]:
    """The period's first and last day, and the opening and closing balances."""
    p = PERIOD.search(text)
    if not p:
        raise ParseError("Period (Fecha Corte: Del … Al …) not found.")
    start, end = _period_date(*p.group(1, 2, 3)), _period_date(*p.group(4, 5, 6))
    o, c = OPENING.search(text), CLOSING.search(text)
    if not o or not c:
        raise ParseError("Opening or closing balance (Saldo inicial / final contable) not found.")
    return start, end, _num(o.group(1)), _num(c.group(1))


def _read_lines(pages: list[str], out: ParsedStatement) -> list[Found]:
    """Every movement as printed, in the text's order; what can't be read goes to the rejects."""
    end = out.period_end
    found: list[Found] = []
    for page_no, line_no, line in numbered_lines(pages):
        m = LINE.match(line)
        if not m:
            if LOOKS_LIKE_LINE.search(line):
                out.rejects.append(Reject(page_no, line_no, line, "Line could not be read"))
            continue
        month = MONTHS[m.group("mon")[:3].lower()]
        year = end.year if month <= end.month else end.year - 1
        try:
            d = date(year, month, int(m.group("day")))
        except ValueError as exc:
            out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            continue
        desc = m.group("desc").strip()
        ln = Line(page_no, line_no, _section(desc), line, d, None, _num(m.group("amt")), desc)
        found.append((ln, m.group("amt"), _num(m.group("bal"))))
    return found


def _in_text_order(found: list[Found], opening: Decimal, out: ParsedStatement) -> Decimal:
    """No order fits every balance (a line is missing or misread): keep the text's order and
    return how far the printed balances stray, line by line."""
    gaps = Decimal(0)
    running = opening
    for ln, raw_amt, bal in found:
        if _sign_lost(raw_amt) and running - ln.amount == bal:
            ln.amount = -ln.amount  # the sign was lost (an OCR read)
        gaps += abs(bal - (running + ln.amount))
        running = bal  # resynchronize so one misprint is counted at most twice
        out.lines.append(ln)
    return gaps


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Produbanco statement: the savings account, or the Visa card when the pages are one."""
    text = "\n".join(pages)
    if produbanco_card.is_card_statement(text):  # the Visa card, not the savings account
        return produbanco_card.parse(pages)
    start, end, opening, closing = _header(text)
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=opening,
        closing_balance=closing,
        totals={"opening": opening, "closing": closing},
    )
    # Every line carries the balance after it, so the lines are put in the bank's order by
    # chaining balances from the opening one: some PDFs give their text out of order (July 2026
    # read Jul 13, then the Jul 31 lines, then Jul 15), which isn't a missing line.
    found = _read_lines(pages, out)
    order = _chain(found, opening)
    gaps = Decimal(0)
    if order is not None:
        for k, sign in order:
            found[k][0].amount *= sign
            out.lines.append(found[k][0])
    else:
        gaps = _in_text_order(found, opening, out)
    moved = sum((ln.amount for ln in out.lines), Decimal(0))
    out.checks += [
        Check("Opening balance + lines = closing balance", closing, opening + moved),
        Check("Gaps in the running balance, line by line", Decimal(0), gaps),
    ]
    return out
