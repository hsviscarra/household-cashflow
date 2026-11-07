from decimal import Decimal
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
    # Statements that tie out (totals, continuity) with no unreadable lines are approved as soon
    # as they're read, and uploads are read right away; the rest wait on the Import page.
    auto_approve: bool = True
    # After a statement is approved on its own, Claude's suggestions this sure or more are
    # accepted with a rule (ADR-029); 0 turns it off. Needs ANTHROPIC_API_KEY.
    auto_accept_confidence: Decimal = Decimal("0.90")
    # Password of the read-only database login the MCP endpoint queries with (SELECT on mart
    # views only). Created or updated at start-up; empty = the endpoint uses the app's login
    # (local development and tests only).
    reader_password: str = ""
    # Whose invoice is it (ADR-036): "Hernan:<cédula>,Lauren:<cédula>". Compared with the
    # buyer's ID while an invoice XML is read; only the name is stored, never the ID.
    invoice_buyers: str = ""
    # Bank sync (ADR-044): the SimpleFIN access URL (holds credentials; a Container App secret,
    # set by infra/azure/setup-simplefin.sh). Empty = sync off.
    simplefin_access_url: str = ""
    # The SRI's public authorization web service (ADR-037): an invoice's XML by its access key.
    sri_authorization_url: str = (
        "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline"
    )
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
