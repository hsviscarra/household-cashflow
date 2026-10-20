"""The shape every statement parser returns (F4 on)."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

CENT = Decimal("0.01")


@dataclass
class Line:
    page: int
    line_no: int
    section: str  # payment, purchase, fee, interest, ...
    text: str
    txn_date: date
    post_date: date | None
    # Signed from the account's side: money out of the household is negative.
    amount: Decimal
    description: str
    cardholder: str | None = None  # last four digits of the card used
    person: str | None = None  # Hernan, Lauren or Joint


@dataclass
class Reject:
    page: int
    line_no: int
    text: str
    reason: str


@dataclass
class Check:
    name: str
    expected: Decimal
    actual: Decimal

    @property
    def ok(self) -> bool:
        return abs(self.expected - self.actual) < CENT / 2


@dataclass
class ParsedStatement:
    parser: str
    period_start: date
    period_end: date
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    totals: dict[str, Decimal]
    lines: list[Line] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def tieout_ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks) and not self.rejects


class ParseError(Exception):
    """The statement does not have the layout this parser expects."""


def money(text: str) -> Decimal:
    return Decimal(text.replace("$", "").replace(",", "").strip())
