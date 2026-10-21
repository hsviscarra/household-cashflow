"""Banco del Pacífico Mastercard (Pacificard) statements, read with OCR (F8b, ADR-005).

The bank's web statement is printed to a PDF that holds a screenshot, so the text comes from
app.ingestion.ocr and may carry OCR noise: "4GO/28" for AGO/28, "W/D" for N/D, "SEP/0S" for
SEP/05, "Cons" for CONS. Amounts are re-read digits-only by the OCR step.

"Periodo de corte desde: 25/AGO/2026 hasta 24/SEP/2026"; under "DETALLE DE MOVIMIENTOS DEL
PERIODO": "SALDO ANTERIOR 400.00", one block per cardholder ("<id> NAME", local
then foreign purchases), lines "SEP/08 100002 SU PAGO PAGO DIRECTO BDP GUAYAQUI PAGO 80.00 -"
(date, reference, description, operation, US$ amount, [foreign amount], +/-), then
"TOTAL PAGO DE CONTADO", "SALDO ACTUAL ROTATIVO / DIFERIDO", "SUBTOTAL CONSUMOS PERIODO",
"SUBTOTAL PAGOS/CREDITOS". Layout notes in docs/parsers.md.
"""

import difflib
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from app.ingestion.detect import ES_MONTHS
from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError, Reject

NAME = "pacificard"
AMT = r"\d{1,3}(?:,?\d{3})*\.\d{2}"
AMOUNT = re.compile(rf"^{AMT}$")
MONTHS = [*ES_MONTHS, "set"]
TO_LETTER = str.maketrans("0425618", "OASZGIB")
TO_DIGIT = str.maketrans("OoSsIlBZ$§", "0055118255")

PERIOD = re.compile(r"desde:?\s*(\S+)\s+hasta:?\s*(\S+)", re.I)
LINE_START = re.compile(r"^(?P<mon>[\w$§]{3})/ ?(?P<day>[\w$§]{1,2}) (?P<rest>.+)$")
OPERATIONS = ("CONS", "PAGO", "INT", "CARG", "N/D", "N/C", "DIF")
# How each operation moves the debt, for the tie-out (the summary box groups them this way).
GROUPS = {"CONS": "purchases", "N/D": "purchases", "DIF": "purchases", "PAGO": "payments"}
GROUPS |= {"N/C": "payments", "INT": "charges", "CARG": "charges"}
HOLDER = re.compile(r"^\S*\d{5,}\S* (?P<name>[A-ZÁÉÍÓÚÑ ]{5,})$")
PEOPLE = ("HERNAN", "LAUREN")
TOTALS = {
    "opening": re.compile(rf"DO ANTERIOR ({AMT})$"),
    "closing": re.compile(rf"^TOTAL PAGO DE CONTADO ({AMT})$"),
    "revolving": re.compile(rf"^SALDO ACTUAL ROTATIVO ({AMT})$"),
    "deferred": re.compile(rf"^SALDO ACTUAL DIFERIDO ({AMT})$"),
    "purchases": re.compile(rf"^SUBTOTAL CONSUMOS \S+ ({AMT})$"),
    "payments": re.compile(rf"^SUBTOTAL PAGOS\S* ({AMT})$"),
    "owed": re.compile(rf"Deuda Total ({AMT}) 100% ({AMT})$"),
}
SUMMARY = re.compile(rf"^({AMT}) ({AMT}) ({AMT}) ({AMT}) ({AMT})$")  # anterior, +, -, +, total


def _num(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _month(token: str) -> list[int]:
    """Candidate months for an OCR'd month name, best first ("4GO" → AGO)."""
    t = token.upper().translate(TO_LETTER).lower()
    if t in MONTHS:
        return [ES_MONTHS.get(t, 9)]
    return [ES_MONTHS.get(m, 9) for m in difflib.get_close_matches(t, MONTHS, n=3, cutoff=0.3)]


def _day(token: str) -> int:
    digits = token.translate(TO_DIGIT)
    if not digits.isdigit():
        raise ValueError(f"day '{token}' is not readable")
    return int(digits)


def _period_date(token: str) -> date | None:
    m = re.fullmatch(r"(\w{1,2})/(\w{3})/(\d{4})", token)
    if not m:
        return None
    try:
        months = _month(m.group(2))
        return date(int(m.group(3)), months[0], _day(m.group(1))) if months else None
    except (ValueError, IndexError):
        return None


def _line_date(mon: str, day: str, start: date, end: date) -> date:
    d = _day(day)
    for month in _month(mon):
        for year in (end.year, end.year - 1):
            try:
                found = date(year, month, d)
            except ValueError:
                continue
            if start - timedelta(days=62) <= found <= end + timedelta(days=7):
                return found
    raise ValueError(f"{mon}/{day} is not a date in the statement period")


def _agreed(values: list[Decimal]) -> Decimal | None:
    """The value most printings agree on (each total is printed two to four times)."""
    if not values:
        return None
    (best, n), *rest = Counter(values).most_common()
    return best if not rest or rest[0][1] < n else values[0]


def _section(op: str, desc: str) -> str:
    upper = desc.upper()
    if op == "PAGO":
        return "payment"
    if op == "INT":
        return "interest"
    if op == "N/C":
        return "credit"
    if op == "CARG" or "COMISION" in upper or upper.startswith("SERV. RENOVACION"):
        return "fee"
    if op == "N/D" or "SOLCA" in upper or "DESGRAVAMEN" in upper:
        return "charge"
    return "purchase"


def _operation(token: str) -> str:
    t = re.sub(r"[^A-Z/]", "", token.upper()).replace("W/D", "N/D")  # "N/D-~", "CONS3"
    for op in OPERATIONS:
        if t == op or (op == "CONS" and t.startswith("CONS")):
            return op
    raise ValueError(f"operation '{token}' not recognized")


def _person(name: str) -> str | None:
    for word in name.split():
        hit = difflib.get_close_matches(word, PEOPLE, n=1, cutoff=0.8)
        if hit:
            return hit[0].capitalize()
    return None  # the account owner


def parse(pages: list[str]) -> ParsedStatement:
    text = "\n".join(pages)
    p = PERIOD.search(text)
    end = _period_date(p.group(2)) if p else None
    if end is None:
        raise ParseError("Period (Periodo de corte desde … hasta …) could not be read.")
    start = _period_date(p.group(1)) if p else None
    if start is None or not end - timedelta(days=40) <= start < end:
        # The start date is sometimes unreadable; the cycle runs from the day after last cut.
        start = (end.replace(day=1) - timedelta(days=1)).replace(day=min(end.day, 28))
        start += timedelta(days=1)

    found: dict[str, list[Decimal]] = {k: [] for k in TOTALS}
    summary: list[tuple[Decimal, ...]] = []
    rows: list[tuple[int, int, str, re.Match[str]]] = []
    holders: list[tuple[int, int, str | None]] = []
    rejects: list[Reject] = []
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            for key, rx in TOTALS.items():
                if t := rx.search(line):
                    found[key] += [_num(g) for g in t.groups()]
            if row := SUMMARY.match(line):
                summary.append(tuple(_num(g) for g in row.groups()))
            if h := HOLDER.match(line):
                holders.append((page_no, line_no, _person(h.group("name"))))
            elif m := LINE_START.match(line):
                rows.append((page_no, line_no, line, m))

    for box in summary:  # the summary box repeats the opening and closing balances
        found["opening"].append(box[0])
        found["closing"].append(box[4])
    opening = _agreed(found["opening"])
    closing = _agreed(found["closing"] + found["revolving"] + found["owed"])
    if opening is None or closing is None:
        raise ParseError("Previous balance or total due could not be read.")
    totals = {"opening": opening, "closing": closing}
    for key in ("purchases", "payments", "deferred"):
        if (v := _agreed(found[key])) is not None:
            totals[key] = v
    if summary:
        totals["charges"] = _agreed([box[3] for box in summary]) or Decimal(0)
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=opening,
        closing_balance=closing,
        totals=totals,
        rejects=rejects,
    )

    moved = {"purchases": Decimal(0), "payments": Decimal(0), "charges": Decimal(0)}
    for page_no, line_no, line, m in rows:
        person = next(
            (who for pg, ln, who in reversed(holders) if (pg, ln) < (page_no, line_no)), None
        )
        tokens = m.group("rest").split()
        try:
            sign = {"+": 1, "=": 1, "-": -1}[tokens[-1]]
            if not AMOUNT.match(tokens[-2]):
                raise ValueError("amount not readable")
            usd = tokens[-3] if AMOUNT.match(tokens[-3]) else tokens[-2]
            op_at = -4 if usd is tokens[-3] else -3
            op = _operation(tokens[op_at])
            when = _line_date(m.group("mon"), m.group("day"), start, end)
        except (KeyError, IndexError, ValueError) as exc:
            rejects.append(Reject(page_no, line_no, line, f"Line could not be read: {exc}"))
            continue
        desc = re.sub(r"^W/D ", "N/D ", " ".join(tokens[1:op_at]))  # tokens[0]: the reference
        moved[GROUPS[op]] += sign * _num(usd)
        out.lines.append(
            Line(
                page=page_no,
                line_no=line_no,
                section=_section(op, desc),
                text=line,
                txn_date=when,
                post_date=None,
                amount=-sign * _num(usd),  # "+" adds to the debt: money out
                description=desc,
                person=person,
            )
        )

    _tie_out(out, moved)
    return out


def _tie_out(out: ParsedStatement, moved: dict[str, Decimal]) -> None:
    t = out.totals
    purchases, charges, paid = moved["purchases"], moved["charges"], -moved["payments"]
    labels = {
        "purchases": ("Purchases and debits (SUBTOTAL CONSUMOS)", purchases),
        "payments": ("Payments and credits (SUBTOTAL PAGOS)", paid),
        "charges": ("Interest and charges", charges),
    }
    for key, (label, actual) in labels.items():
        if key in t:
            out.checks.append(Check(label, t[key], actual))
    out.checks.append(
        Check(
            "Previous balance + purchases - payments + charges = total due",
            t["closing"],
            t["opening"] + purchases - paid + charges,
        )
    )
    if "deferred" in t:  # deferred purchases aren't seen on Pacificard yet; stop if they appear
        out.checks.append(Check("Deferred balance (none expected)", Decimal(0), t["deferred"]))
