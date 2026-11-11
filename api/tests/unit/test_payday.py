"""ADR-070: a salary paid on the 1st or 2nd counts in the month before."""

from datetime import date
from decimal import Decimal

from app.services.payday import cash_month


def test_early_payroll_counts_in_the_month_before() -> None:
    assert cash_month(date(2026, 10, 1), "ROL DE PAGOS", Decimal("3798.73")) == date(2026, 9, 1)
    assert cash_month(date(2026, 1, 2), "rol  de pagos", Decimal("10")) == date(2025, 12, 1)


def test_other_lines_count_in_their_month() -> None:
    assert cash_month(date(2026, 10, 27), "ROL DE PAGOS", Decimal("3886.76")) == date(2026, 10, 1)
    assert cash_month(date(2026, 10, 3), "ROL DE PAGOS", Decimal("1")) == date(2026, 10, 1)
    assert cash_month(date(2026, 10, 1), "ROL DE PAGOS", Decimal("-5")) == date(2026, 10, 1)
    assert cash_month(date(2026, 10, 1), "DEBITO ECUASANITAS", Decimal("5")) == date(2026, 10, 1)
