"""Backup status for Data Status (F17, ADR-016): the latest backup and restore drill, read from
the manifests the jobs write (app.ops.backup), and whether either is overdue.

A backup is overdue when the newest one finished more than 36 hours ago (the export runs
nightly); a drill when the newest one is more than 40 days old (it runs monthly) or failed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.ops.backup import (
    BackupStore,
    BlobBackupStore,
    LocalBackupStore,
    latest_backup,
    latest_drill,
)

BACKUP_EVERY = timedelta(hours=36)
DRILL_EVERY = timedelta(days=40)


@dataclass
class BackupStatus:
    where: str  # azure or local
    backup: dict[str, Any] | None
    drill: dict[str, Any] | None
    backup_overdue: bool
    drill_overdue: bool
    error: str | None = None


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@lru_cache
def get_backup_store() -> BackupStore:
    """FastAPI dependency; tests override it with a folder."""
    s = get_settings()
    if s.storage_account_url:  # pragma: no cover - Azure
        return BlobBackupStore(s.storage_account_url, s.backups_container)
    return LocalBackupStore(s.backups_dir)


def status(store: BackupStore, now: datetime | None = None) -> BackupStatus:
    now = now or datetime.now(UTC)
    where = "azure" if get_settings().storage_account_url else "local"
    try:
        backup, drill = latest_backup(store), latest_drill(store)
    except Exception as exc:  # storage unreachable: say so instead of failing the page
        return BackupStatus(where, None, None, True, True, f"Backups can't be read: {exc}")
    if backup is not None:
        backup = {
            k: backup.get(k)
            for k in ("file", "finished_at", "size", "migration", "transaction_total", "seconds")
        } | {"rows": sum((backup.get("tables") or {}).values())}
    done = _when(backup["finished_at"]) if backup else None
    tried = _when(drill.get("finished_at")) if drill else None
    return BackupStatus(
        where,
        backup,
        drill,
        backup_overdue=done is None or now - done > BACKUP_EVERY,
        drill_overdue=tried is None or now - tried > DRILL_EVERY or not (drill or {}).get("ok"),
    )
