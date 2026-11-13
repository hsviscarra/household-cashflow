"""Month status (F12, ADR-009): is each month complete, and if not, what is missing.

A month the Excel history covers is complete by definition (ADR-004). From the month after it up
to the current month, a month is complete when nothing below is open:
- statements: every active account has approved statements covering every day of the month (card
  statements run mid-month to mid-month, so coverage is counted by day);
- imports: no statement for the month waits for approval or fails its tie-out;
- lines without a category, and transfers without their other side (F10);
- recurring items expected and not paid (F11);
- balance breaks: a statement's opening balance differs from the previous statement's closing
  balance for the same account.
"""

from app.services.status.arrival import EMAIL_LAG, EMAILED, how_it_arrives, sources
from app.services.status.base import (
    DASH,
    DAY,
    AccountTimeline,
    Coverage,
    Gap,
    Item,
    Load,
    MonthStatus,
    Source,
    Status,
    TimelineStatement,
    _days,
    month_end,
)
from app.services.status.months import (
    EXCEL_MONTHS_SHOWN,
    Period,
    _balance_breaks,
    loads,
    month_status,
)
from app.services.status.statements import (
    FILE_NAMES,
    SHOWN_BILLS,
    SYNC_FRESH,
    _file_names,
    _gaps,
    _Stmt,
    approved_statements,
    next_cycle_end,
    not_loaded,
    prev_cycle_end,
    statement_closes,
    statement_files,
    sync_coverage,
    timeline,
)

__all__ = [
    "DASH",
    "DAY",
    "EMAILED",
    "EMAIL_LAG",
    "EXCEL_MONTHS_SHOWN",
    "FILE_NAMES",
    "SHOWN_BILLS",
    "SYNC_FRESH",
    "AccountTimeline",
    "Coverage",
    "Gap",
    "Item",
    "Load",
    "MonthStatus",
    "Period",
    "Source",
    "Status",
    "TimelineStatement",
    "_Stmt",
    "_balance_breaks",
    "_days",
    "_file_names",
    "_gaps",
    "approved_statements",
    "how_it_arrives",
    "loads",
    "month_end",
    "month_status",
    "next_cycle_end",
    "not_loaded",
    "prev_cycle_end",
    "sources",
    "statement_closes",
    "statement_files",
    "sync_coverage",
    "timeline",
]
