"""ADR-099: a view of spending built from two dimensions and a measure."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services import explore
from app.services.explore import Record, Spec

D = Decimal
OCT, NOV = date(2026, 10, 1), date(2026, 11, 1)


def _spec(**kwargs: Any) -> Spec:
    base: dict[str, Any] = {
        "measure": "amount",
        "rows": "group",
        "cols": None,
        "start": OCT,
        "end": NOV,
    }
    return Spec(**{**base, **kwargs})


FOUND = [
    Record("Groceries", "2026-10", D(300), 3),
    Record("Groceries", "2026-11", D(100), 1),
    Record("Dining", "2026-10", D(90), 3),
]


def test_pivot_amounts_lines_and_averages() -> None:
    p = explore.pivot(FOUND, _spec(cols="month"))
    assert (p.rows, p.cols) == (["Groceries", "Dining"], ["2026-10", "2026-11"])  # biggest first
    assert p.cells == [[D(300), D(100)], [D(90), D(0)]]
    assert (p.row_totals, p.col_totals, p.total) == ([D(400), D(90)], [D(390), D(100)], D(490))
    lines = explore.pivot(FOUND, _spec(cols="month", measure="lines"))
    assert lines.cells == [[D(3), D(1)], [D(3), D(0)]] and lines.total == 7
    # An average is the sum over the lines in every cell and every total: 400 / 4, 490 / 7.
    avg = explore.pivot(FOUND, _spec(cols="month", measure="average"))
    assert avg.cells[1] == [D("30.00"), D(0)]
    assert (avg.row_totals, avg.total) == ([D("100.00"), D("30.00")], D("70.00"))
    one = explore.pivot([Record("Groceries", "", D(400), 4)], _spec())
    assert (one.cols, one.col_totals, one.cells, one.total) == ([], [], [[D(400)]], D(400))
    assert explore.pivot([], _spec()).rows == []


def test_time_reads_in_order_and_what_does_not_fit_is_added_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_month = [Record("2026-11", "", D(1), 1), Record("2026-10", "", D(900), 1)]
    assert explore.pivot(by_month, _spec(rows="month")).rows == ["2026-10", "2026-11"]
    monkeypatch.setattr(explore, "MAX_ROWS", 1)
    p = explore.pivot(FOUND, _spec(cols="month"))
    assert (p.rows, p.folded) == (["Groceries", explore.REST], 1)
    assert p.cells[1] == [D(90), D(0)] and p.total == D(490)
    # Too many months: the latest are kept, nothing is folded.
    late = explore.pivot(by_month, _spec(rows="month"))
    assert (late.rows, late.folded, late.total) == (["2026-11"], 0, D(1))


def test_what_can_be_asked() -> None:
    explore.check(_spec())
    for bad, why in (
        (_spec(measure="median"), "Measure is one of"),
        (_spec(rows="colour"), "Rows and columns are one of"),
        (_spec(cols="group"), "can't be the same"),
        (_spec(start=NOV, end=OCT), "starts after it ends"),
        (_spec(start=date(2020, 1, 1)), "at most 60 months"),
    ):
        with pytest.raises(explore.ExploreError, match=why):
            explore.check(bad)
    assert explore.label("account", None) == "Cash Flow sheet"
    assert explore.label("person", None) == explore.NOT_SET
    assert (explore.label("kind", True), explore.label("kind", False)) == ("Fixed", "Variable")
    assert (explore.label("month", OCT), explore.label("year", OCT)) == ("2026-10", "2026")


def _line(db: Session, n: int, day: date, amount: str, category: str, person: str) -> None:
    bank = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    cat = db.scalar(select(Category).where(Category.name == category))
    assert bank is not None and cat is not None
    db.add(
        Transaction(
            natural_key=f"exp-{n}",
            account_id=bank.account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=D(amount),
            description_raw=f"LINE {n}",
            merchant="SUPERMAXI" if category == "Supermarket" else None,
            type="expense",
            category_id=cat.category_id,
            person=person,
            source="manual",
            status="confirmed",
        )
    )


def test_from_the_lines_through_the_api(client: TestClient, db: Session) -> None:
    _line(db, 1, date(2026, 10, 5), "-200", "Supermarket", "Hernan")
    _line(db, 2, date(2026, 10, 9), "-100", "Supermarket", "Lauren")
    _line(db, 3, date(2026, 11, 2), "-100", "Supermarket", "Hernan")
    _line(db, 4, date(2026, 10, 20), "-90", "Doctors", "Lauren")
    _line(db, 5, date(2025, 12, 20), "-999", "Doctors", "Lauren")  # outside the period
    db.commit()

    def get(**params: Any) -> Any:
        return client.get(
            "/api/explore", params={"start": "2026-10-01", "end": "2026-11-01", **params}
        )

    out = get(rows="group", cols="month").json()
    assert (out["rows"], out["cols"]) == (["Groceries", "Health"], ["2026-10", "2026-11"])
    assert out["cells"] == [["300.0000", "100.0000"], ["90.0000", "0"]]
    assert D(out["total"]) == D(490) and out["folded"] == 0
    # Month and year share a column in the database: grouped once, read as both.
    years = get(rows="year", cols="month").json()
    assert years["rows"] == ["2026"] and [D(x) for x in years["cells"][0]] == [D(390), D(100)]
    who = get(rows="person", measure="lines", group_id=_group(db, "Groceries")).json()
    assert (who["rows"], who["row_totals"], who["cols"]) == (["Hernan", "Lauren"], ["2", "1"], [])
    # A line without a merchant goes by its description, as on every spending page.
    assert get(rows="merchant", person="Lauren").json()["rows"] == ["SUPERMAXI", "LINE 4"]
    kinds = get(rows="kind", measure="average").json()
    assert kinds["rows"] == ["Variable"] and D(kinds["total"]) == D("122.50")
    assert get(rows="group", cols="group").status_code == 422
    assert get(rows="group", measure="median").status_code == 422


def _group(db: Session, name: str) -> int:
    g = db.scalar(select(Category).where(Category.name == name, Category.parent_id.is_(None)))
    assert g is not None, name
    return g.category_id
