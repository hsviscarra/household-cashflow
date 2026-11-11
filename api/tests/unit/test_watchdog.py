"""ADR-078: the Gmail script's heartbeat and the alerts it emails, each once."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import status as status_service
from app.services import watchdog

TOKEN = {"Authorization": "Bearer inbox-secret"}


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INBOX_TOKEN", "inbox-secret")
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
    assert client.get("/api/inbox/alerts").status_code == 401
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

    first = client.get("/api/inbox/alerts", headers=TOKEN).json()
    assert [a["title"] for a in first["alerts"]] == ["Diners Club Hernan: statement is late"]
    assert first["subject"] == "Cash flow: Diners Club Hernan: statement is late"
    assert "Closed Nov 3." in first["text"] and "/status" in first["text"]
    assert watchdog.script(db).state == "ok"  # the call checked in

    again = client.get("/api/inbox/alerts", headers=TOKEN).json()
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
    both = client.get("/api/inbox/alerts", headers=TOKEN).json()
    assert len(both["alerts"]) == 2 and both["subject"] == "Cash flow: 2 things need you"


def test_status_and_claude_see_the_script(client: TestClient, db: Session) -> None:
    assert client.get("/api/status").json()["script"]["state"] == "never"
    watchdog.check_in(db, datetime(2026, 1, 1))
    got = client.get("/api/status").json()["script"]
    assert got["state"] == "silent" and got["last_seen"].startswith("2026-01-01")
