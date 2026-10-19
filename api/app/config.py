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

    @property
    def allowed_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.allowed_emails.split(",") if e.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
