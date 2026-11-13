"""ADR-068: a paused Azure SQL database is woken up instead of failing the first login."""

from typing import Any

import pytest

from app import db


class FakeDialect:
    def __init__(self, fails: list[str]) -> None:
        self.fails = fails
        self.tries = 0

    def connect(self, *a: Any, **k: Any) -> str:
        self.tries += 1
        if self.fails:
            raise RuntimeError(self.fails.pop(0))
        return "connection"


def test_waking_errors_are_recognised() -> None:
    assert db.waking(RuntimeError("[HYT00] Login timeout expired (0)"))
    assert db.waking(RuntimeError("Database 'x' on server 'y' is not currently available (40613)"))
    assert not db.waking(RuntimeError("Login failed for user 'cashflow_reader'. (18456)"))


def test_the_login_is_tried_again_while_the_database_wakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    d = FakeDialect(["[HYT00] Login timeout expired", "(40613) not currently available"])
    out = db.connect_waking(d.connect)
    assert out == "connection" and d.tries == 3


def test_a_wrong_password_fails_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    d = FakeDialect(["Login failed for user (18456)"])
    with pytest.raises(RuntimeError):
        db.connect_waking(d.connect)
    assert d.tries == 1


def test_after_the_last_try_the_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    d = FakeDialect(["HYT00"] * 5)
    with pytest.raises(RuntimeError):
        db.connect_waking(d.connect)
    assert d.tries == len(db.WAITS) + 1


def test_sql_server_keeps_no_idle_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-092: an open pooled connection is a session, and a session keeps Azure SQL awake."""
    from sqlalchemy.pool import NullPool, QueuePool

    asked: list[dict[str, Any]] = []
    real = db.create_engine

    def fake(url: Any, **kw: Any) -> Any:
        asked.append(kw)
        return real("sqlite:///:memory:")  # the driver for SQL Server isn't needed to check this

    monkeypatch.setattr(db, "create_engine", fake)
    db.make_engine("mssql+pyodbc://u:p@example.database.windows.net/cashflow?driver=x")
    assert asked[-1]["poolclass"] is NullPool and "pool_recycle" not in asked[-1]
    db.make_engine("mssql+pyodbc://u:p@h/db?driver=x", poolclass=QueuePool)
    assert asked[-1]["poolclass"] is QueuePool  # a caller can still ask for one
    db.make_engine("sqlite:///:memory:")
    assert "poolclass" not in asked[-1] and asked[-1]["pool_pre_ping"] is True
