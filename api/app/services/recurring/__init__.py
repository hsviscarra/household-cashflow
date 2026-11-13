"""Recurring entries (F11, ADR-008).

A template is a row that repeats every month (salary, rent, condo fee, the card payment). Its
amount is kept from a month on (core.recurring_amount), so "change from month X" is one row. Each
month gets one entry per active template with the expected amount; a cell edited by hand (or
copied) is an override and template changes leave it alone.

Matching links the month's lines to the entries they pay (transaction.recurring_entry_id):
- months covered by the Excel history link only Excel lines, and a template made from a workbook
  row links that row's cell exactly, whatever its amount;
- other months link statement and manual lines of the template's category (or still without a
  category when the template has a pattern), on its account (the line's or its matched transfer's
  other side) and containing its pattern when those are set, within the tolerance (a percentage of
  the expected amount, at least 1.00);
- one line close enough wins; otherwise several lines that only this entry can take are linked
  together when their sum is within tolerance (a salary paid in two halves).
A matched entry is never re-matched; unlinking or skipping frees its lines.
"""

from app.services.recurring.base import (
    CENT,
    EVERY,
    EXCEL_SHEET,
    INCOME_TYPES,
    MIN_TOLERANCE,
    RecurringError,
    active_in,
    add_months,
    amount_for,
    amounts,
    due_in,
    first,
    get_entry,
    get_template,
    months,
    signed,
)
from app.services.recurring.bill_list import IN_CHUNK, PRICE_RECENT, Bill, bills, data_through
from app.services.recurring.matching import (
    candidates,
    excel_months,
    link_line,
    match,
    match_all,
    recategorized,
    tolerance,
    unlink_line,
)
from app.services.recurring.templates import (
    EDITABLE,
    MAX_COPY_MONTHS,
    change_amount,
    copy,
    create_template,
    delete_entry,
    delete_template,
    edit_entry,
    generate,
    stop,
    update_template,
)
from app.services.recurring.year_grid import (
    Cell,
    ExcelRow,
    Grid,
    Row,
    create_from_excel,
    excel_rows,
    grid,
    plan_by_month,
)

__all__ = [
    "CENT",
    "EDITABLE",
    "EVERY",
    "EXCEL_SHEET",
    "INCOME_TYPES",
    "IN_CHUNK",
    "MAX_COPY_MONTHS",
    "MIN_TOLERANCE",
    "PRICE_RECENT",
    "Bill",
    "Cell",
    "ExcelRow",
    "Grid",
    "RecurringError",
    "Row",
    "active_in",
    "add_months",
    "amount_for",
    "amounts",
    "bills",
    "candidates",
    "change_amount",
    "copy",
    "create_from_excel",
    "create_template",
    "data_through",
    "delete_entry",
    "delete_template",
    "due_in",
    "edit_entry",
    "excel_months",
    "excel_rows",
    "first",
    "generate",
    "get_entry",
    "get_template",
    "grid",
    "link_line",
    "match",
    "match_all",
    "months",
    "plan_by_month",
    "recategorized",
    "signed",
    "stop",
    "tolerance",
    "unlink_line",
    "update_template",
]
