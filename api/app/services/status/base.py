"""What Data Status is made of: a month's items and coverage, an account's timeline, the loads."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.models import (
    Account,
)
from app.services import recurring

DAY = timedelta(days=1)
DASH = "\u2013"


def month_end(month: date) -> date:
    """The last day of a month."""
    return recurring.add_months(month, 1) - DAY


def _days(start: date, end: date) -> str:
    """'Oct 22-31', 'Oct 5', 'Sep 28-Oct 3' (with an en dash)."""
    if start == end:
        return f"{start:%b} {start.day}"
    if start.month == end.month:
        return f"{start:%b} {start.day}{DASH}{end.day}"
    return f"{start:%b} {start.day}{DASH}{end:%b} {end.day}"


@dataclass
class Item:
    """Something a month still needs."""

    kind: str  # statement, import, uncategorized, transfer, recurring, balance, note
    text: str
    link: str
    count: int = 1


@dataclass
class Coverage:
    """How many of a month's days an account's statements cover."""

    account_id: int
    covered_days: int
    days: int

    @property
    def state(self) -> str:
        """Whether the month's days are fully, partly or not covered by data."""
        if self.covered_days >= self.days:
            return "full"
        return "partial" if self.covered_days else "none"


@dataclass
class MonthStatus:
    """A month's source, what it needs and its coverage."""

    month: date
    source: str  # excel or statements
    items: list[Item] = field(default_factory=list)
    coverage: list[Coverage] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Whether nothing is left to do for the month."""
        return not self.items


@dataclass
class Load:
    """A load: when, from what and by whom."""

    loaded_at: datetime
    source: str
    file_name: str | None
    rows: int
    loaded_by: str


@dataclass
class TimelineStatement:
    """A statement on an account's timeline."""

    file_id: int
    file_name: str
    start: date
    end: date
    state: str  # loaded, waiting, problems (read, doesn't tie out), not_read, synced
    batch_id: int | None


@dataclass
class Gap:
    """A period an account has no statement for."""

    start: date
    end: date
    # Set when the gap is the current cycle, whose statement the bank hasn't issued yet.
    due: date | None = None
    # The statements that fill it, by the day each closes, and their usual file names where the
    # bank puts the date in them ("Statement_112026_4003.pdf" closes in November 2026).
    closes: list[date] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class AccountTimeline:
    """An account's statements and gaps."""

    account_id: int
    name: str
    closed_on: date | None
    opened_on: date | None
    start_day: int | None  # the day of the month its statements usually start
    statements: list[TimelineStatement]
    gaps: list[Gap]


@dataclass
class Source:
    """How an account's data arrives and where it stands today (ADR-072)."""

    account_id: int
    name: str
    how: str  # bank_sync, email, upload
    last_day: date | None  # the last day its loaded data covers
    state: str  # up_to_date, on_its_way, on_import, you_upload, late
    note: str
    expected: date | None = None  # when the next data should be there


@dataclass
class Status:
    """The state of the data: accounts, months, loads and the timeline."""

    today: date
    excel_through: date | None
    accounts: list[Account]
    months: list[MonthStatus]
    loads: list[Load]
    timeline: list[AccountTimeline] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
