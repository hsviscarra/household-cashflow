"""Capital One credit card statements (Venture). Layout notes in docs/parsers.md.

Page 1 has the account summary; the Transactions pages list lines per cardholder
("NAME #1234: Payments, Credits and Adjustments" / "NAME #1234: Transactions"), each line as
"Sep 2 Sep 4 UBER EATS SAN JOSE $12.38" (payments print "- $4,000.00"), then Fees and
Interest Charged sections. Dates carry no year; the billing cycle supplies it.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError, Reject, money

NAME = "capitalone"
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
AMT = r"\$[\d,]+\.\d{2}"

PERIOD = re.compile(rf"(({MONTHS}) \d{{2}}, \d{{4}}) - (({MONTHS}) \d{{2}}, \d{{4}})")
SUMMARY = {
    "previous_balance": re.compile(rf"Previous Balance ({AMT})"),
    "payments": re.compile(rf"Payments - ({AMT})"),
    "other_credits": re.compile(rf"Other Credits ({AMT})"),
    "transactions": re.compile(rf"Transactions \+ ({AMT})"),
    "cash_advances": re.compile(rf"Cash Advances \+ ({AMT})"),
    "fees": re.compile(rf"Fees Charged \+ ({AMT})"),
    "interest": re.compile(rf"Interest Charged \+ ({AMT})"),
    "new_balance": re.compile(rf"New Balance = ({AMT})"),
}
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


def _year_for(day_month: str, start: date, end: date) -> date:
    """ "Sep 2" inside a Sep 4 - Oct 3 cycle: the year that puts it nearest the cycle."""
    for year in (end.year, end.year - 1, end.year + 1):
        d = datetime.strptime(f"{day_month} {year}", "%b %d %Y").date()
        if start - timedelta(days=62) <= d <= end + timedelta(days=7):
            return d
    raise ValueError(f"{day_month} is outside the billing cycle")


def parse(pages: list[str]) -> ParsedStatement:
    text = "\n".join(pages)
    m = PERIOD.search(text)
    if not m:
        raise ParseError("Billing cycle (e.g. 'Sep 04, 2026 - Oct 03, 2026') not found.")
    start = datetime.strptime(m.group(1), "%b %d, %Y").date()
    end = datetime.strptime(m.group(3), "%b %d, %Y").date()

    totals: dict[str, Decimal] = {}
    for key, rx in SUMMARY.items():
        found = rx.search(text)
        if not found:
            raise ParseError(f"Account summary line '{key}' not found.")
        totals[key] = money(found.group(1))

    out = ParsedStatement(
        parser=NAME,
        period_start=start,
        period_end=end,
        opening_balance=totals["previous_balance"],
        closing_balance=totals["new_balance"],
        totals=totals,
    )

    card_totals: dict[str, Decimal] = {}
    section: str | None = None
    card: str | None = None
    person: str | None = None
    for page_no, page in enumerate(pages, start=1):
        for line_no, raw in enumerate(page.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            if ct := CARD_TOTAL.search(line):
                card_totals[ct.group(1)] = money(ct.group(2))
                continue
            if h := CARDHOLDER.match(line):
                card = h.group("card")
                person = next((PEOPLE[w] for w in h.group("name").split() if w in PEOPLE), None)
                what = h.group("what").lower()
                section = "payment" if what.startswith("payments") else "purchase"
                continue
            matched_total = False
            for key, rx in PERIOD_TOTALS.items():
                if t := rx.match(line):
                    totals[key] = money(t.group(1))
                    matched_total = True
            if matched_total:
                continue
            if line == "Fees":
                section, card, person = "fee", None, None
                continue
            if line == "Interest Charged":
                section, card, person = "interest", None, None
                continue
            if line.startswith("Totals Year-to-Date") or line.startswith(
                "Interest Charge Calculation"
            ):
                section = None
                continue
            if section == "interest" and (i := INTEREST_LINE.match(line)):
                amount = money(i.group(2))
                if amount:
                    out.lines.append(
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
                continue
            if not (t := LINE.match(line)):
                continue
            if section not in ("payment", "purchase", "fee"):
                out.rejects.append(
                    Reject(page_no, line_no, line, "Transaction outside a known section")
                )
                continue
            try:
                td = _year_for(t.group("td"), start, end)
                pd = _year_for(t.group("pd"), start, end)
            except ValueError as exc:
                out.rejects.append(Reject(page_no, line_no, line, str(exc)))
                continue
            amount = money(t.group("amt"))
            signed = amount if t.group("neg") else -amount  # charges reduce money; credits add
            out.lines.append(
                Line(
                    page_no,
                    line_no,
                    section,
                    line,
                    td,
                    pd,
                    signed,
                    t.group("desc").strip(),
                    card,
                    person if section != "fee" else "Joint",
                )
            )

    _tie_out(out, card_totals)
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
        Check("Payments and credits", t["payments"] + t["other_credits"], total("payment")),
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
