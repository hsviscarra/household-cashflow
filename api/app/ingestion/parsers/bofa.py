"""Bank of America combined statements: checking and savings in one PDF (F5).

Page 1 lists the accounts ("Adv Plus Banking 4460 3033 8872 $6,856.04"). Each account then has
"Account number: 4460 3033 8872", an Account summary (Beginning balance on August 22, 2026 $X,
Deposits and other additions X, Withdrawals and other subtractions -X, Checks -X, Service fees -X,
Ending balance on ... $X) and sections of lines "08/28/26 Description -25.00". A description can
wrap onto the next lines (e.g. "ID:9279744380 WEB"), even across a page break. Continuation pages
carry "Account # 4460 3033 8872" in their header. Layout notes in docs/parsers.md.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.ingestion.parsers.base import (
    Check,
    Line,
    ParsedStatement,
    ParseError,
    Reject,
    money,
    numbered_lines,
)

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


MAX_CONTINUATION_CHARS = 60  # a wrapped description's extra line is short


def _period(text: str) -> tuple[date, date]:
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Statement period (e.g. 'for August 22, 2026 to ...') not found.")
    return (
        datetime.strptime(m.group(1), "%B %d, %Y").date(),
        datetime.strptime(m.group(2), "%B %d, %Y").date(),
    )


@dataclass
class _Reader:
    """Reads the statement line by line, remembering which account and section it is in. Each
    `_take_*` method says whether the line was its kind; `read` tries them in order."""

    out: ParsedStatement
    summary: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    printed: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    begin: dict[str, Decimal] = field(default_factory=dict)
    ending: dict[str, Decimal] = field(default_factory=dict)
    account: str | None = None
    section: str | None = None
    in_summary: bool = False
    last: Line | None = None
    continued: int = 0

    def read(self, page_no: int, line_no: int, line: str) -> None:
        """Read one non-empty line."""
        if self._take_account(line) or self.account is None:
            return
        if self._take_summary(line, self.account) or self._take_heading(line, self.account):
            return
        if self._take_movement(page_no, line_no, line):
            return
        self._take_continuation(line)

    def _take_account(self, line: str) -> bool:
        """The start of an account, or a continuation page's header naming it."""
        if a := ACCOUNT.search(line):
            self.account, self.section, self.in_summary, self.last = a.group(1), None, False, None
            return True
        if a := PAGE_ACCOUNT.search(line):
            self.account = a.group(1)
            return True
        return False

    def _take_summary(self, line: str, account: str) -> bool:
        """The account summary: its balances and each section's amount."""
        if line == "Account summary":
            self.in_summary = True
            return True
        if b := BEGIN.match(line):
            self.begin[account] = money(b.group(1))
            return True
        if e := END.match(line):
            self.ending[account] = money(e.group(1))
            self.in_summary = False
            return True
        if not self.in_summary:
            return False
        label, _, amount = line.rpartition(" ")
        if (sec := _section_of(label)) and re.fullmatch(AMT, amount):
            self.summary.setdefault(account, {})[sec] = money(amount)
        return True

    def _take_heading(self, line: str, account: str) -> bool:
        """A section's header, its column header on a continuation page, or its printed total."""
        if (sec := _section_of(line)) is not None:
            self.section, self.last = sec, None
            return True
        if line.startswith("Date ") and line.endswith("Amount"):
            # A header on a continuation page: the next short lines may finish the last line.
            self.continued = 0
            return True
        if t := TOTAL.match(line):
            sec = _section_of(t.group("what"))
            if sec:
                self.printed[(account, sec)] = money(t.group("amt"))
            self.last = None
            return True
        return False

    def _take_movement(self, page_no: int, line_no: int, line: str) -> bool:
        """A dated line with an amount: a movement, or a reject when it can't be placed."""
        m = LINE.match(line)
        if not m:
            return False
        if self.section is None:
            self.out.rejects.append(Reject(page_no, line_no, line, "Line outside a known section"))
            return True
        try:
            d = _date(m.group("d"))
        except ValueError as exc:
            self.out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            return True
        desc = m.group("desc").strip()
        ref = REFERENCE.search(desc)
        self.last = Line(
            page_no, line_no, self.section, line, d, None, money(m.group("amt")), desc,
            None, "Joint", self.account, ref.group(1) if ref else None,
        )  # fmt: skip
        self.out.lines.append(self.last)
        self.continued = 0
        return True

    def _take_continuation(self, line: str) -> None:
        """A short line after a movement finishes its description, unless it is page furniture."""
        low = line.lower()
        furniture = any(low.startswith(s) for s in STOP_CONTINUING)
        fits = self.continued < MAX_CONTINUATION and len(line) <= MAX_CONTINUATION_CHARS
        if self.last is not None and fits:
            if furniture:
                self.last = None if low.startswith("total ") else self.last
                self.continued = MAX_CONTINUATION
                return
            self.last.description = f"{self.last.description} {line}"
            self.continued += 1
        elif furniture:
            self.continued = MAX_CONTINUATION


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Bank of America statement's pages: period, balances, lines and tie-out checks."""
    start, end = _period("\n".join(pages))
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=None,
        closing_balance=None,
        totals={},
    )
    reader = _Reader(out)
    for page_no, line_no, line in numbered_lines(pages):
        if line:
            reader.read(page_no, line_no, line)
    if not reader.begin:
        raise ParseError("No 'Account number' sections with a beginning balance found.")
    out.balances = {a: (reader.begin[a], reader.ending.get(a, Decimal(0))) for a in reader.begin}
    for acct, (opening, closing) in out.balances.items():
        out.totals[f"{acct}_beginning"] = opening
        out.totals[f"{acct}_ending"] = closing
    _tie_out(out, reader.summary, reader.printed)
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
