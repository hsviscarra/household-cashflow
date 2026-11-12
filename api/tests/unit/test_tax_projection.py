"""ADR-088: the year's income tax, projected. Synthetic data; the table is the SRI's for 2026."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AppSetting, Category, Transaction
from app.services import projections, tax_projection
from app.services.tax_projection import Profile, tax_on

D = Decimal


@pytest.mark.parametrize(
    ("taxable", "expected"),
    [
        ("0", "0.00"),
        ("12208", "0.00"),  # the top of the 0% band
        ("12208.01", "0.00"),  # 5% of one cent rounds to nothing
        ("15549", "167.05"),  # 5% of 3,341
        ("20188", "630.90"),  # 167 + 10% of 4,639 (the next band starts at 631)
        ("30000", "1907.00"),  # 1,412 + 15% of 3,300
        ("36000", "2850.80"),  # 2,678 + 20% of 864
        ("109956", "24571.95"),  # 15,025 + 35% of 27,277
        ("150000", "39388.28"),  # 24,572 + 37% of 40,044
    ],
)
def test_the_sri_table_for_2026(taxable: str, expected: str) -> None:
    assert tax_on(D(taxable), 2026) == D(expected)


def test_a_year_without_a_table() -> None:
    with pytest.raises(tax_projection.TaxError, match="2031"):
        tax_on(D(1), 2031)


def _salary(db: Session, person: str, day: date, amount: str, source: str = "statement") -> None:
    cat = db.scalar(select(Category).where(Category.name == person))
    acct = db.scalars(select(Account)).first()
    assert cat is not None and acct is not None
    db.add(
        Transaction(
            natural_key=f"tax-{person}-{day}-{source}",
            account_id=acct.account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=D(amount),
            description_raw="PAYROLL",
            type="income",
            category_id=cat.category_id,
            source=source,
        )
    )


def test_income_projected_tax_and_what_to_set_aside(client: TestClient, db: Session) -> None:
    # Hernan is paid 3,000 on the 20th, January to October; today is Nov 12.
    for m in range(1, 11):
        _salary(db, "Hernan", date(2026, m, 20), "3000")
    # Lauren: 1,500 a month net; her employer withholds.
    for m in range(1, 11):
        _salary(db, "Lauren", date(2026, m, 28), "1500")
    db.commit()
    today = {"today": "2026-11-12"}
    h, lau = client.get("/api/taxes/2026/projection", params=today).json()

    assert h["person"] == "Hernan" and h["profile"]["regime"] == "foreign"
    assert h["received"] == "30000.00" and h["typical_month"] == "3000.00"
    assert h["projected_income"] == "36000.00" and h["taxable"] == "36000.00"
    assert h["tax"] == "2850.80"
    # No invoices yet: no rebate, and the whole cap (7 baskets of 821.80) is room.
    assert h["rebate"] == "0.00" and h["cap"] == "5752.60" and h["room"] == "5752.60"
    assert h["more_rebate"] == "1035.47"  # 18% of the cap
    assert h["due"] == "2850.80" and h["to_pay"] == "2850.80"
    assert h["pay_on"] == "2027-03-15" and h["months_left"] == 4
    assert h["set_aside"] == "712.70"
    assert any("Nothing is withheld" in n for n in h["notes"])

    assert lau["profile"]["regime"] == "employee"
    assert lau["projected_income"] == "18000.00" and lau["tax"] == "412.10"  # 167 + 10% of 2,451
    assert any("Nothing entered as withheld" in n for n in lau["notes"])

    # Lauren's payslips: 300 withheld in the year, 1,900 of décimos in her deposits.
    out = client.put(
        "/api/taxes/2026/projection/Lauren",
        params=today,
        json={"regime": "employee", "withheld": "300", "exempt": "1900", "deductions": "0"},
    )
    assert out.status_code == 200, out.text
    lau = out.json()
    assert lau["taxable"] == "16400.00"  # 18,000 + 300 - 1,900
    assert lau["tax"] == "252.10" and lau["to_pay"] == "-47.90"  # in her favour
    assert lau["set_aside"] == "0.00" and lau["notes"] == []
    assert db.get(AppSetting, "tax-profile:2026:Lauren") is not None
    bad = client.put(
        "/api/taxes/2026/projection/Lauren", json={"regime": "employee", "withheld": "-1"}
    )
    assert bad.status_code == 422
    assert client.get("/api/taxes/2031/projection").status_code == 404

    # The forecast carries Hernan's payment in March; Lauren owes nothing.
    pays = tax_projection.payments(db, date(2026, 11, 12), date(2027, 11, 30))
    assert pays == [(date(2027, 3, 15), "Income tax 2026, Hernan (estimate)", D("2850.80"))]
    plan = projections.project(db, date(2026, 11, 12), horizon=12)
    march = next(m for m in plan.months if m.month == date(2027, 3, 1))
    assert any(e.name.startswith("Income tax 2026, Hernan") for e in march.items)


def test_a_workbook_month_is_not_counted_twice(db: Session) -> None:
    # January is in the workbook and also has a statement line; statements count from February.
    _salary(db, "Hernan", date(2026, 1, 1), "3000", source="excel_history")
    _salary(db, "Hernan", date(2026, 1, 20), "3000")
    _salary(db, "Hernan", date(2026, 2, 20), "3100")
    db.add(AppSetting(setting_key="statements_from", setting_value="2026-02-01", updated_by="t"))
    db.commit()
    t = tax_projection.person_tax(db, "Hernan", 2026, date(2026, 3, 5))
    assert t.received == D("6100.00")
    # March to December count the typical month (the median of January and February).
    assert t.typical_month == D("3050.00") and t.projected_income == D("36600.00")


def test_an_unreadable_profile_falls_back(db: Session) -> None:
    db.add(AppSetting(setting_key="tax-profile:2026:Hernan", setting_value="x", updated_by="t"))
    db.commit()
    assert tax_projection.profile(db, "Hernan", 2026) == Profile("foreign")
    with pytest.raises(tax_projection.TaxError):
        tax_projection.set_profile(db, "Juli", 2026, Profile("employee"), "t")
