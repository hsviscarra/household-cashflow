"""Which month a line's money counts in (ADR-070).

Lines count in the month of their date, except a salary paid on the first days of a month for the
month before: Lauren's payroll ("ROL DE PAGOS") sometimes lands on the 1st, and counting it then
leaves one month with no salary and the next with two.
"""

from datetime import date, timedelta
from decimal import Decimal

EARLY_PAY = ("ROL DE PAGOS",)
EARLY_DAYS = 2  # paid on the 1st or 2nd → the month before


def cash_month(txn_date: date, description: str, amount: Decimal) -> date:
    first = txn_date.replace(day=1)
    text = " ".join(description.upper().split())
    if amount > 0 and txn_date.day <= EARLY_DAYS and any(p in text for p in EARLY_PAY):
        return (first - timedelta(days=1)).replace(day=1)
    return first
