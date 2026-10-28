"""The read-only database login for Claude's MCP endpoint (F18, ADR-017).

`cashflow_reader` belongs to the `mart_reader` role (migration 0018), which may only SELECT from
the `mart` views; the views read the core tables through ownership chaining, so the login can't
read a table directly or change anything. At start-up (infra/docker/entrypoint.sh) the app,
connected with its own login, creates the user or sets its password from READER_PASSWORD:
- Azure SQL Database: a contained database user with a password;
- SQL Server (local): a server login and a database user for it.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from app.config import get_settings
from app.db import get_engine

READER = "cashflow_reader"
ROLE = "mart_reader"


def _quoted(password: str) -> str:
    return password.replace("'", "''")


def ensure_reader() -> str:
    s = get_settings()
    if not s.reader_password:
        return "ensure_reader: skipped (READER_PASSWORD not set)"
    pw = _quoted(s.reader_password)
    with get_engine().connect() as conn:
        azure = conn.execute(text("SELECT CAST(SERVERPROPERTY('EngineEdition') AS INT)")).scalar()
        if azure == 5:  # Azure SQL Database: contained user
            conn.execute(
                text(
                    f"IF USER_ID(N'{READER}') IS NULL "
                    f"CREATE USER [{READER}] WITH PASSWORD = N'{pw}' "
                    f"ELSE ALTER USER [{READER}] WITH PASSWORD = N'{pw}';"
                )
            )
        else:  # SQL Server: a login, then the user
            conn.execute(
                text(
                    f"IF SUSER_ID(N'{READER}') IS NULL "
                    f"CREATE LOGIN [{READER}] WITH PASSWORD = N'{pw}' "
                    f"ELSE ALTER LOGIN [{READER}] WITH PASSWORD = N'{pw}';"
                )
            )
            conn.execute(
                text(
                    f"IF USER_ID(N'{READER}') IS NULL CREATE USER [{READER}] FOR LOGIN [{READER}];"
                )
            )
        conn.execute(
            text(
                f"IF IS_ROLEMEMBER(N'{ROLE}', N'{READER}') = 0 "
                f"ALTER ROLE [{ROLE}] ADD MEMBER [{READER}];"
            )
        )
        conn.commit()
    return f"ensure_reader: [{READER}] ready"


def reader_url() -> URL:
    """The app's database URL with the read-only login in place of the app's."""
    s = get_settings()
    return make_url(s.database_url).set(username=READER, password=s.reader_password)


@lru_cache
def get_reader_engine() -> Engine:
    """The MCP endpoint's engine: the read-only login when READER_PASSWORD is set."""
    if not get_settings().reader_password:
        return get_engine()
    return create_engine(reader_url(), pool_pre_ping=True, pool_recycle=1800)


if __name__ == "__main__":  # pragma: no cover
    print(ensure_reader())
