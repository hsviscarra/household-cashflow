"""Capital One credit card statements (Venture). Layout notes in docs/parsers.md.

Page 1 has the account summary; the Transactions pages list lines per cardholder
("NAME #1234: Payments, Credits and Adjustments" / "NAME #1234: Transactions"), each line as
"Sep 2 Sep 4 UBER EATS SAN JOSE $12.38" (payments print "- $4,000.00"), then Fees and
Interest Charged sections. Dates carry no year; the billing cycle supplies it.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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

NAME = "capitalone"
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
AMT = r"\$[\d,]+\.\d{2}"

PERIOD = re.compile(rf"(({MONTHS}) \d{{2}}, \d{{4}}) - (({MONTHS}) \d{{2}}, \d{{4}})")
SUMMARY = {
    "previous_balance": re.compile(rf"Previous Balance ({AMT})"),
    "payments": re.compile(rf"Payments - ({AMT})"),
    # "Other Credits $0.00", or with a minus like Payments when there is one: "- $14.76".
    "other_credits": re.compile(rf"Other Credits (?:- )?({AMT})"),
    "transactions": re.compile(rf"Transactions \+ ({AMT})"),
    "cash_advances": re.compile(rf"Cash Advances \+ ({AMT})"),
    "fees": re.compile(rf"Fees Charged \+ ({AMT})"),
    "interest": re.compile(rf"Interest Charged \+ ({AMT})"),
    "new_balance": re.compile(rf"New Balance = ({AMT})"),
}
PAYMENT = re.compile(r"\b(?:PYMT|PAYMENT|AUTOPAY)\b", re.I)  # "CAPITAL ONE MOBILE PYMT"
CARDHOLDER = re.compile(r"^(?P<name>[A-Z][A-Z .'-]+) #(?P<card>\d{4}): (?P<what>.+)$")
LINE = re.compile(
    rf"^(?P<td>(?:{MONTHS}) \d{{1,2}}) (?P<pd>(?:{MONTHS}) \d{{1,2}}) (?P<desc>.+?) "
    rf"(?P<neg>- )?(?P<amt>{AMT})$"
)
CARD_TOTAL = re.compile(rf"#(\d{{4}}): Total Transactions ({AMT})$")
PERIOD_TOTALS = {
    "period_transactions": re.compile(rf"^Total Transactions for This Period ({AMT})$"),
    "period_fees": re.compile(rf"^Total Fees for This Period ({AMT})$"),
    "period_interest": re.compile(rf"^Total Interest for This Period ({AMT})$"),
}
INTEREST_LINE = re.compile(rf"^(Interest Charge on [A-Za-z ]+) ({AMT})$")
PEOPLE = {"HERNAN": "Hernan", "LAUREN": "Lauren"}
# The sections that belong to the account, not to a cardholder.
SECTION_TITLES = {"Fees": "fee", "Interest Charged": "interest"}
END_OF_LINES = ("Totals Year-to-Date", "Interest Charge Calculation")


def _year_for(day_month: str, start: date, end: date) -> date:
    """ "Sep 2" inside a Sep 4 - Oct 3 cycle: the year that puts it nearest the cycle."""
    for year in (end.year, end.year - 1, end.year + 1):
        d = datetime.strptime(f"{day_month} {year}", "%b %d %Y").date()
        if start - timedelta(days=62) <= d <= end + timedelta(days=7):
            return d
    raise ValueError(f"{day_month} is outside the billing cycle")


def _period(text: str) -> tuple[date, date]:
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Billing cycle (e.g. 'Sep 04, 2026 - Oct 03, 2026') not found.")
    return (
        datetime.strptime(m.group(1), "%b %d, %Y").date(),
        datetime.strptime(m.group(3), "%b %d, %Y").date(),
    )


def _summary(text: str) -> dict[str, Decimal]:
    """The account summary's amounts; every one of them must be there."""
    totals: dict[str, Decimal] = {}
    for key, rx in SUMMARY.items():
        found = rx.search(text)
        if not found:
            raise ParseError(f"Account summary line '{key}' not found.")
        totals[key] = money(found.group(1))
    return totals


@dataclass
class _Reader:
    """Reads the transaction pages line by line, remembering the section and whose card it is.
    Each `_take_*` method says whether the line was its kind; `read` tries them in order."""

    out: ParsedStatement
    card_totals: dict[str, Decimal] = field(default_factory=dict)
    section: str | None = None
    card: str | None = None
    person: str | None = None

    def read(self, page_no: int, line_no: int, line: str) -> None:
        """Read one non-empty line."""
        if self._take_heading(line) or self._take_interest(page_no, line_no, line):
            return
        self._take_transaction(page_no, line_no, line)

    def _take_heading(self, line: str) -> bool:
        """A card's total, a cardholder's section, a period total, or a section's title."""
        if ct := CARD_TOTAL.search(line):
            self.card_totals[ct.group(1)] = money(ct.group(2))
            return True
        if h := CARDHOLDER.match(line):
            self.card = h.group("card")
            self.person = next((PEOPLE[w] for w in h.group("name").split() if w in PEOPLE), None)
            what = h.group("what").lower()
            self.section = "payment" if what.startswith("payments") else "purchase"
            return True
        matched_total = False
        for key, rx in PERIOD_TOTALS.items():
            if t := rx.match(line):
                self.out.totals[key] = money(t.group(1))
                matched_total = True
        if matched_total:
            return True
        if line in SECTION_TITLES:
            self.section, self.card, self.person = SECTION_TITLES[line], None, None
            return True
        if line.startswith(END_OF_LINES):
            self.section = None
            return True
        return False

    def _take_interest(self, page_no: int, line_no: int, line: str) -> bool:
        """An interest charge, dated the cycle's last day; a zero one isn't a line."""
        if self.section != "interest" or not (i := INTEREST_LINE.match(line)):
            return False
        amount = money(i.group(2))
        end = self.out.period_end
        if amount:
            self.out.lines.append(
                Line(
                    page_no,
                    line_no,
                    "interest",
                    line,
                    end,
                    end,
                    -amount,
                    i.group(1).upper(),
                    None,
                    "Joint",
                )
            )
        return True

    def _take_transaction(self, page_no: int, line_no: int, line: str) -> None:
        """A dated line with an amount: a movement, or a reject when it can't be placed."""
        t = LINE.match(line)
        if not t:
            return
        out = self.out
        if self.section not in ("payment", "purchase", "fee"):
            out.rejects.append(
                Reject(page_no, line_no, line, "Transaction outside a known section")
            )
            return
        try:
            td = _year_for(t.group("td"), out.period_start, out.period_end)
            pd = _year_for(t.group("pd"), out.period_start, out.period_end)
        except ValueError as exc:
            out.rejects.append(Reject(page_no, line_no, line, str(exc)))
            return
        amount = money(t.group("amt"))
        signed = amount if t.group("neg") else -amount  # charges reduce money; credits add
        desc = t.group("desc").strip()
        # "Payments, Credits and Adjustments" also lists refunds ("AMAZON MKTPLACE PMTS…"):
        # only a payment to the card is a payment (a transfer); the rest is money back.
        refund = self.section == "payment" and not PAYMENT.search(desc)
        out.lines.append(
            Line(
                page_no,
                line_no,
                "credit" if refund else self.section,
                line,
                td,
                pd,
                signed,
                desc,
                self.card,
                self.person if self.section != "fee" else "Joint",
            )
        )


def parse(pages: list[str]) -> ParsedStatement:
    """Read a Capital One statement's pages: cycle, balances, lines by cardholder and checks."""
    text = "\n".join(pages)
    start, end = _period(text)
    totals = _summary(text)
    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=totals["previous_balance"],
        closing_balance=totals["new_balance"],
        totals=totals,
    )
    reader = _Reader(out)
    for page_no, line_no, line in numbered_lines(pages):
        if line:
            reader.read(page_no, line_no, line)
    _tie_out(out, reader.card_totals)
    return out


def _tie_out(out: ParsedStatement, card_totals: dict[str, Decimal]) -> None:
    t = out.totals

    def total(section: str, card: str | None = None) -> Decimal:
        return sum(
            (
                ln.amount
                for ln in out.lines
                if ln.section == section and (card is None or ln.cardholder == card)
            ),
            Decimal(0),
        )

    for card, printed in sorted(card_totals.items()):
        out.checks.append(Check(f"Card #{card} transactions", printed, -total("purchase", card)))
    purchases = -total("purchase")
    out.checks += [
        Check("Transactions, all cards", t["transactions"], purchases),
        Check(
            "Total transactions for the period", t.get("period_transactions", purchases), purchases
        ),
        Check(
            "Payments and credits",
            t["payments"] + t["other_credits"],
            total("payment") + total("credit"),
        ),
        Check("Fees", t["fees"], -total("fee")),
        Check("Interest", t["interest"], -total("interest")),
        Check(
            "Previous balance - payments + charges = new balance",
            t["new_balance"],
            t["previous_balance"]
            - t["payments"]
            - t["other_credits"]
            + t["transactions"]
            + t["cash_advances"]
            + t["fees"]
            + t["interest"],
        ),
    ]
