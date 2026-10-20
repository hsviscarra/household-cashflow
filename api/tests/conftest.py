"""Unit-test database: the core models on in-memory SQLite, seeded with seed v1."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_session
from app.main import create_app
from app.models import Account, Base, Category, MerchantRule
from app.routers.health import database_check
from app.seeds import load_v1


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(eng, "connect")
    def _attach(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS core")
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        load_v1(conn, Account.__table__, Category.__table__, MerchantRule.__table__)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[database_check] = lambda: lambda: True
    yield TestClient(app)
