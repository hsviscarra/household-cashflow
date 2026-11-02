from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db import get_engine

_factory: sessionmaker[Session] | None = None


def _sessions() -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the route when it writes."""
    with _sessions()() as session:
        yield session


def get_session_factory() -> Callable[[], Session]:
    """FastAPI dependency for work that runs after the response (a background task): it opens its
    own session, because the request's is closed by then."""
    return _sessions()
