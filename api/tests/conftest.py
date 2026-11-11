"""Unit-test database: all models on in-memory SQLite, seeded with seeds v1 and v2, plus the mart
views. SQLite has no schemas, so every schema maps to the main database."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Most tests walk through read -> preview -> approve by hand; tests of automatic approval
# (ADR-024) turn it on themselves.
os.environ.setdefault("AUTO_APPROVE", "false")

from app.db.session import get_session, get_session_factory
from app.ingestion.storage import LocalStore, get_store
from app.main import create_app
from app.models import Account, Base, Category, MerchantRule
from app.routers.health import database_check
from app.seeds import (
    load_v1,
    load_v2,
    load_v3,
    load_v4,
    load_v5,
    load_v6,
    load_v7,
    load_v8,
    load_v9,
    load_v10,
    load_v11,
)

SCHEMAS = {s: None for s in ("raw", "stg", "rej", "core", "mart", "audit")}
VIEW_DIR = Path(__file__).resolve().parents[1] / "migrations" / "views"


def _sqlite_view(sql: str) -> str:
    return re.sub(r"\[(raw|stg|rej|core|mart|audit)\]\.", "", sql)


@pytest.fixture
def engine() -> Iterator[Engine]:
    base = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(base, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    eng = base.execution_options(schema_translate_map=SCHEMAS)
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        load_v1(conn, Account.__table__, Category.__table__, MerchantRule.__table__)
        load_v2(conn, Category.__table__)
        load_v3(conn, Account.__table__, Category.__table__, MerchantRule.__table__)
        load_v4(conn, Category.__table__, MerchantRule.__table__)
        load_v5(conn, Category.__table__)
        load_v6(conn, Account.__table__, Category.__table__, MerchantRule.__table__)
        load_v7(conn, Category.__table__, MerchantRule.__table__)
        load_v8(conn, Category.__table__)
        load_v9(conn, Category.__table__)
        load_v10(conn, Category.__table__, MerchantRule.__table__)
        load_v11(conn, Category.__table__, MerchantRule.__table__)
        for path in sorted(VIEW_DIR.glob("*.sql")):
            conn.execute(text(_sqlite_view(path.read_text(encoding="utf-8"))))
    yield eng  # type: ignore[misc]
    base.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "statements")


@pytest.fixture
def client(engine: Engine, store: LocalStore) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[database_check] = lambda: lambda: True
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
