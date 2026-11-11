"""ADR-078: the Gmail script's heartbeat and the alerts it emails, each once."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import status as status_service
from app.services import watchdog

TOKEN = {"Authorization": "Bearer inbox-secret"}


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INBOX_TOKEN", "inbox-secret")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("INBOX_TOKEN")
    get_settings.cache_clear()


def _late(monkeypatch: pytest.MonkeyPatch, *sources: status_service.Source) -> None:
    real = status_service.month_status

    def fake(db: Session, today: date | None = None, with_loads: bool = True) -> object:
        st = real(db, today, with_loads)
        st.sources = list(sources)
        return st

    monkeypatch.setattr(status_service, "month_status", fake)


def test_heartbeat_states(db: Session) -> None:
    now = datetime(2026, 11, 11, 11, 0)
    assert watchdog.script(db, now).state == "never"
    watchdog.check_in(db, now - timedelta(hours=30))
    ok = watchdog.script(db, now)
    assert ok.state == "ok" and ok.last_seen == now - timedelta(hours=30)
    watchdog.check_in(db, now - timedelta(days=3, hours=1))
    silent = watchdog.script(db, now)
    assert silent.state == "silent" and "3 days ago (Nov 8)" in silent.note


def test_alerts_come_once_and_the_call_is_the_heartbeat(
    client: TestClient, db: Session, inbox: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/inbox", params={"alerts": True}).status_code == 401
    diners = status_service.Source(
        7,
        "Diners Club Hernan",
        "email",
        date(2026, 10, 3),
        "late",
        "Closed Nov 3.",
        date(2026, 11, 10),
    )
    fine = status_service.Source(8, "BofA", "bank_sync", date(2026, 11, 11), "up_to_date", "")
    _late(monkeypatch, diners, fine)

    first = client.get("/api/inbox", params={"alerts": True}, headers=TOKEN).json()
    assert [a["title"] for a in first["alerts"]] == ["Diners Club Hernan: statement is late"]
    assert first["subject"] == "Cash flow: Diners Club Hernan: statement is late"
    assert "Closed Nov 3." in first["text"] and "/status" in first["text"]
    assert watchdog.script(db).state == "ok"  # the call checked in

    again = client.get("/api/inbox", params={"alerts": True}, headers=TOKEN).json()
    assert again["alerts"] == [] and again["text"] == ""

    # The next statement of the same account is a new alert; two at once share a subject.
    later = status_service.Source(
        7,
        "Diners Club Hernan",
        "email",
        date(2026, 11, 3),
        "late",
        "Closed Dec 3.",
        date(2026, 12, 10),
    )
    other = status_service.Source(
        9,
        "Banco Pichincha",
        "email",
        date(2026, 11, 8),
        "late",
        "Closed Dec 8.",
        date(2026, 12, 15),
    )
    _late(monkeypatch, later, other)
    both = client.get("/api/inbox", params={"alerts": True}, headers=TOKEN).json()
    assert len(both["alerts"]) == 2 and both["subject"] == "Cash flow: 2 things need you"


def test_status_and_claude_see_the_script(client: TestClient, db: Session) -> None:
    assert client.get("/api/status").json()["script"]["state"] == "never"
    watchdog.check_in(db, datetime(2026, 1, 1))
    got = client.get("/api/status").json()["script"]
    assert got["state"] == "silent" and got["last_seen"].startswith("2026-01-01")


def test_more_kinds_and_turning_them_off(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-082: bills, budgets, unusual charges and large transfers join the late statements;
    each kind can be turned off, and one that fails doesn't stop the rest."""
    from decimal import Decimal
    from types import SimpleNamespace

    from app.services import budget, digest, recurring, transfers

    today = date(2026, 11, 11)
    _late(monkeypatch)  # no late statements
    monkeypatch.setattr(
        digest,
        "_unusual",
        lambda db, t: [digest.Item("ACME: 300.00 on Nov 09, usually about 40.00", "/x")],
    )
    bill = SimpleNamespace(
        template_id=4, name="Internet", expected=Decimal("-45.00"), status="due", due_day=13
    )
    paid = SimpleNamespace(
        template_id=5, name="Rent", expected=Decimal("-500"), status="paid", due_day=12
    )
    far = SimpleNamespace(
        template_id=6, name="Gym", expected=Decimal("-30"), status="due", due_day=25
    )
    late = SimpleNamespace(
        template_id=7, name="Water", expected=Decimal("-20"), status="late", due_day=5
    )
    monkeypatch.setattr(recurring, "bills", lambda db, m, t: [bill, paid, far, late])
    groups = [
        SimpleNamespace(
            group_id=1,
            name="Dining",
            budget=Decimal(200),
            available=Decimal(200),
            spent=Decimal(170),
        ),
        SimpleNamespace(
            group_id=2,
            name="Transport",
            budget=Decimal(100),
            available=Decimal(100),
            spent=Decimal(130),
        ),
        SimpleNamespace(
            group_id=3,
            name="Health",
            budget=Decimal(100),
            available=Decimal(100),
            spent=Decimal(10),
        ),
        SimpleNamespace(
            group_id=4, name="Gifts", budget=None, available=Decimal(0), spent=Decimal(50)
        ),
    ]
    monkeypatch.setattr(budget, "month_view", lambda db, m, t: SimpleNamespace(groups=groups))

    def boom(_db: Session) -> list[object]:
        raise RuntimeError("down")

    monkeypatch.setattr(transfers, "unmatched", boom)

    titles = [a.title for a in watchdog.alerts(db, today)]
    assert titles == [
        "Unusual charge",
        "Internet is due in 2 days",
        "Water is late",
        "Dining is at 85% of its budget of 200.00",
        "Transport is over its budget: 130.00 of 100.00",
    ]

    big = SimpleNamespace(
        transaction_id=9,
        amount=Decimal("-900"),
        txn_date=date(2026, 10, 25),
        description_raw="WIRE OUT",
    )
    small = SimpleNamespace(
        transaction_id=10, amount=Decimal("-90"), txn_date=date(2026, 10, 25), description_raw="X"
    )
    new = SimpleNamespace(
        transaction_id=11, amount=Decimal("-900"), txn_date=date(2026, 11, 9), description_raw="Y"
    )
    monkeypatch.setattr(transfers, "unmatched", lambda db: [big, small, new])
    assert [a.key for a in watchdog.alerts(db, today) if a.key.startswith("transfer")] == [
        "transfer:9"
    ]

    got = client.get("/api/alerts").json()
    assert [k["key"] for k in got["kinds"]] == ["late", "unusual", "bill", "budget", "transfer"]
    assert all(k["on"] for k in got["kinds"])
    saved = client.put("/api/alerts", json={"off": ["budget", "unusual", "nonsense"]}).json()
    assert {k["key"] for k in saved["kinds"] if not k["on"]} == {"budget", "unusual"}
    assert watchdog.off(db) == {"budget", "unusual"}
    left = [a.key.split(":")[0] for a in watchdog.alerts(db, today)]
    assert set(left) == {"bill", "transfer"}
