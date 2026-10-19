from alembic import context
from sqlalchemy import create_engine, text

from app.config import get_settings

config = context.config


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url, literal_binds=True, version_table_schema="audit"
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        # The alembic version table lives in [audit], so that schema must exist first.
        connection.execute(text("IF SCHEMA_ID(N'audit') IS NULL EXEC(N'CREATE SCHEMA [audit]');"))
        connection.commit()
        context.configure(connection=connection, version_table_schema="audit")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
