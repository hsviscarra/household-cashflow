"""Create the application database on a local SQL Server container if it does not exist.

Only runs when APP_ENV=local. In Azure the database is created by Bicep on the free offer;
creating one from code there could provision a billed database, so this is skipped.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    if settings.app_env != "local":
        print(f"ensure_database: skipped (APP_ENV={settings.app_env})")
        return
    url = make_url(settings.database_url)
    db_name = url.database
    if not db_name or not db_name.replace("_", "").isalnum():
        raise ValueError(f"Unexpected database name: {db_name!r}")
    master = create_engine(url.set(database="master"), isolation_level="AUTOCOMMIT")
    with master.connect() as conn:
        conn.execute(text(f"IF DB_ID(N'{db_name}') IS NULL CREATE DATABASE [{db_name}];"))
    print(f"ensure_database: [{db_name}] ready")


if __name__ == "__main__":
    main()
