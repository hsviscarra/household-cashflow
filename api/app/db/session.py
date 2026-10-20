from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db import get_engine

_factory: sessionmaker[Session] | None = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the route when it writes."""
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with _factory() as session:
        yield session
