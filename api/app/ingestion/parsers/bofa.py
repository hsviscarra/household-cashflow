"""Bank of America combined statements: checking and savings in one PDF (F5).

Page 1 lists the accounts ("Adv Plus Banking 4460 3033 8872 $6,856.04"). Each account then has
"Account number: 4460 3033 8872", an Account summary (Beginning balance on August 22, 2026 $X,
Deposits and other additions X, Withdrawals and other subtractions -X, Checks -X, Service fees -X,
Ending balance on ... $X) and sections of lines "08/28/26 Description -25.00". A description can
wrap onto the next lines (e.g. "ID:9279744380 WEB"), even across a page break. Continuation pages
carry "Account # 4460 3033 8872" in their header. Layout notes in docs/parsers.md.
"""

import re
from datetime import date, datetime
from decimal import Decimal

from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError, Reject, money

NAME = "bofa"
AMT = r"-?\$?[\d,]+\.\d{2}"

PERIOD = re.compile(r"for (\w+ \d{1,2}, \d{4}) to (\w+ \d{1,2}, \d{4})")
ACCOUNT = re.compile(r"Account number: \d{4} \d{4} (\d{4})")
PAGE_ACCOUNT = re.compile(r"Account # \d{4} \d{4} (\d{4})")
BEGIN = re.compile(rf"^Beginning balance on \w+ \d{{1,2}}, \d{{4}} ({AMT})$")
END = re.compile(rf"^Ending balance on \w+ \d{{1,2}}, \d{{4}} ({AMT})$")
LINE = re.compile(rf"^(?P<d>\d{{2}}/\d{{2}}/\d{{2}}) (?P<desc>.+?) (?P<amt>{AMT})$")
REFERENCE = re.compile(r';\s*"([^"]{1,40})"')

# Section header → (section name, summary label). Summary lines repeat the label with an amount.
SECTIONS = {
    "deposits and other additions": "deposit",
    "withdrawals and other subtractions": "withdrawal",
    "atm and debit card subtractions": "card",
    "checks": "check",
    "service fees": "fee",
}
TOTAL = re.compile(rf"^Total (?P<what>[a-z ,]+?) (?P<amt>{AMT})$", re.IGNORECASE)
STOP_CONTINUING = (
    "continued on the next page",
    "total ",
    "note your ending balance",
    "page ",
    "braille and large print",
    "pause and verify",
)
MAX_CONTINUATION = 2


def _date(text: str) -> date:
    return datetime.strptime(text, "%m/%d/%y").date()


def _section_of(text: str) -> str | None:
    key = text.lower().removesuffix(" - continued").strip()
    return SECTIONS.get(key)


def parse(pages: list[str]) -> ParsedStatement:
    text = "\n".join(pages)
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Statement period (e.g. 'for August 22, 2026 to ...') not found.")
    start = datetime.strptime(m.group(1), "%B %d, %Y").date()
    end = datetime.strptime(m.group(2), "%B %d, %Y").date()

    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=None,
        closing_balance=None,
        totals={},
    )
    summary: dict[str, dict[str, Decimal]] = {}
    printed: dict[tuple[str, str], Decimal] = {}
    begin: dict[str, Decimal] = {}
    ending: dict[str, Decimal] = {}

    account: str | None = None
    section: str | None = None
    in_summary = False
    last: Line | None = None
    continued = 0
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            if a := ACCOUNT.search(line):
                account, section, in_summary, last = a.group(1), None, False, None
                continue
            if a := PAGE_ACCOUNT.search(line):
                account = a.group(1)
                continue
            if account is None:
                continue
            if line == "Account summary":
                in_summary = True
                continue
            if b := BEGIN.match(line):
                begin[account] = money(b.group(1))
                continue
            if e := END.match(line):
                ending[account] = money(e.group(1))
                in_summary = False
                continue
            if in_summary:
                label, _, amount = line.rpartition(" ")
                if (sec := _section_of(label)) and re.fullmatch(AMT, amount):
                    summary.setdefault(account, {})[sec] = money(amount)
                continue
            if (sec := _section_of(line)) is not None:
                section, last = sec, None
                continue
            if line.startswith("Date ") and line.endswith("Amount"):
                # A header on a continuation page: the next short lines may finish the last line.
                continued = 0
                continue
            if t := TOTAL.match(line):
                sec = _section_of(t.group("what"))
                if sec:
                    printed[(account, sec)] = money(t.group("amt"))
                last = None
                continue
            if (t2 := LINE.match(line)) and section is not None:
                try:
                    d = _date(t2.group("d"))
                except ValueError as exc:
                    out.rejects.append(Reject(page_no, line_no, line, str(exc)))
                    continue
                desc = t2.group("desc").strip()
                ref = REFERENCE.search(desc)
                last = Line(
                    page_no, line_no, section, line, d, None, money(t2.group("amt")), desc,
                    None, "Joint", account, ref.group(1) if ref else None,
                )  # fmt: skip
                out.lines.append(last)
                continued = 0
                continue
            if t2 and section is None:
                out.rejects.append(Reject(page_no, line_no, line, "Line outside a known section"))
                continue
            low = line.lower()
            if last is not None and continued < MAX_CONTINUATION and len(line) <= 60:
                if any(low.startswith(s) for s in STOP_CONTINUING):
                    last = None if low.startswith("total ") else last
                    continued = MAX_CONTINUATION
                    continue
                last.description = f"{last.description} {line}"
                continued += 1
            elif any(low.startswith(s) for s in STOP_CONTINUING):
                continued = MAX_CONTINUATION

    if not begin:
        raise ParseError("No 'Account number' sections with a beginning balance found.")
    out.balances = {acct: (begin[acct], ending.get(acct, Decimal(0))) for acct in begin}
    for acct, (opening, closing) in out.balances.items():
        out.totals[f"{acct}_beginning"] = opening
        out.totals[f"{acct}_ending"] = closing
    _tie_out(out, summary, printed)
    return out


def _tie_out(
    out: ParsedStatement,
    summary: dict[str, dict[str, Decimal]],
    printed: dict[tuple[str, str], Decimal],
) -> None:
    for acct, (opening, closing) in out.balances.items():
        lines = [ln for ln in out.lines if ln.account == acct]

        def total(section: str, lines: list[Line] = lines) -> Decimal:
            return sum((ln.amount for ln in lines if ln.section == section), Decimal(0))

        for sec, amount in sorted(summary.get(acct, {}).items()):
            if not amount and not any(ln.section == sec for ln in lines):
                continue  # an empty section (e.g. "Checks -0.00") has nothing to check
            out.checks.append(Check(f"•••• {acct} {_LABEL[sec]}", amount, total(sec)))
            if (acct, sec) in printed:
                name = f"•••• {acct} {_LABEL[sec]} (section total)"
                out.checks.append(Check(name, printed[(acct, sec)], total(sec)))
        out.checks.append(
            Check(
                f"•••• {acct} beginning balance + lines = ending balance",
                closing,
                opening + sum((ln.amount for ln in lines), Decimal(0)),
            )
        )


_LABEL = {
    "deposit": "deposits",
    "withdrawal": "withdrawals",
    "card": "card subtractions",
    "check": "checks",
    "fee": "service fees",
}
