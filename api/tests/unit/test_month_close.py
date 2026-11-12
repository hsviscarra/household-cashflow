"""ADR-087: closing a month. Synthetic data only."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services import month_close, report, watchdog
from tests.unit.test_report_api import USER, loaded  # noqa: F401  (the July-October fixture)


def test_ready_from_the_third() -> None:
    assert month_close.last_month(date(2026, 11, 12)) == date(2026, 10, 1)
    assert month_close.ready_on(date(2026, 10, 1)) == date(2026, 11, 3)
    assert month_close.ready_on(date(2026, 12, 15)) == date(2027, 1, 3)


def test_the_screen_shows_only_the_exceptions(loaded: TestClient) -> None:  # noqa: F811
    c = loaded.get("/api/close/2026-10", params={"today": "2026-11-02"}).json()
    assert c["month"] == "2026-10-01" and c["ready_on"] == "2026-11-03"
    assert c["ready"] is False and c["closed_at"] is None and c["has_report"] is False
    # Dining doubled in October against its three months before.
    assert [(u["group"], u["amount"], u["average"]) for u in c["unusual"]] == [
        ("Dining", "300.00", "150.00")
    ]
    assert c["invoices"] == 0 and c["decided"] == []
    assert c["sri_url"].startswith("https://srienlinea.sri.gob.ec")
    # Too early to close.
    early = loaded.post("/api/close/2026-10", params={"today": "2026-11-02"}, headers=USER)
    assert early.status_code == 422 and "November 3" in early.json()["detail"]
    assert loaded.get("/api/close/2027-01", params={"today": "2026-11-02"}).status_code == 422
    assert loaded.get("/api/close/october").status_code == 422


def test_close_writes_the_report_and_can_be_reopened(
    loaded: TestClient,  # noqa: F811
    db: Session,
) -> None:
    day = {"today": "2026-11-03"}
    c = loaded.post("/api/close/2026-10", params=day, headers=USER).json()
    assert c["ready"] is True and c["has_report"] is True
    assert c["closed_by"] == "hernan@example.com" and c["closed_at"] is not None
    assert report.get(db, date(2026, 10, 1)) is not None
    assert db.get(AppSetting, "month-closed:2026-10") is not None
    again = loaded.get("/api/close/2026-10", params=day).json()
    assert again["closed_by"] == "hernan@example.com"
    opened = loaded.delete("/api/close/2026-10", params=day).json()
    assert opened["closed_at"] is None and opened["has_report"] is True


def test_the_check_in_prepares_the_month_and_says_so_once(
    loaded: TestClient,  # noqa: F811
    db: Session,
) -> None:
    assert month_close.prepare(db, date(2026, 11, 2)) is None  # before the 3rd
    assert report.get(db, date(2026, 10, 1)) is None
    ready = month_close.prepare(db, date(2026, 11, 3))
    assert ready is not None and ready.has_report
    found = [a for a in watchdog.alerts(db, date(2026, 11, 3)) if a.key == "close:2026-10"]
    assert [a.title for a in found] == ["October is ready to close"]
    assert "open Close the month" in found[0].text
    month_close.close(db, date(2026, 10, 1), "lauren@example.com", date(2026, 11, 4))
    assert month_close.prepare(db, date(2026, 11, 4)) is None  # closed: nothing more to say
    assert not [a for a in watchdog.alerts(db, date(2026, 11, 4)) if a.key.startswith("close:")]


def test_an_unreadable_record_counts_as_open(db: Session) -> None:
    db.add(AppSetting(setting_key="month-closed:2026-09", setting_value="x", updated_by="t"))
    db.commit()
    assert month_close.view(db, date(2026, 9, 1), date(2026, 11, 3)).closed_at is None
