from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    # SQLAlchemy URL, e.g. mssql+pyodbc://sa:pwd@localhost:1433/cashflow?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
    database_url: str = ""
    # Directory with the built React app; served at / when present.
    web_dist_dir: str = "web_dist"
    git_sha: str = "dev"
    # Comma-separated emails allowed to use the app behind Container Apps auth.
    # Empty = no allow-list (local development, where there is no sign-in).
    allowed_emails: str = ""
    # Statement PDFs: Azure Blob (managed identity) when STORAGE_ACCOUNT_URL is set,
    # otherwise a local folder (a Docker volume in compose).
    storage_account_url: str = ""
    statements_container: str = "statements"
    statements_dir: str = "data/statements"
    # Claude's read-only MCP endpoint (F18): /mcp answers only with this bearer token; empty = off.
    mcp_token: str = ""
    # Statements by email (F20): the Gmail script posts PDFs to /api/inbox with this bearer token;
    # empty = the endpoint is off.
    inbox_token: str = ""
    # Password of the read-only database login the MCP endpoint queries with (SELECT on mart
    # views only). Created or updated at start-up; empty = the endpoint uses the app's login
    # (local development and tests only).
    reader_password: str = ""
    # Backups (F17): the jobs write to this container (Azure) or folder (local runs).
    backups_container: str = "backups"
    backups_dir: str = "data/backups"
    # Claude suggestions for merchants no rule knows (F9). Empty key = suggestions are off.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    # The monthly report's findings (F16): a few careful sentences once a month.
    anthropic_report_model: str = "claude-sonnet-5-5"

    @property
    def allowed_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.allowed_emails.split(",") if e.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
