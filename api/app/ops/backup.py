"""Nightly database export and monthly restore drill (F17, ADR-016).

    python -m app.ops.backup export   # BACPAC of the database, then its manifest
    python -m app.ops.backup drill    # restore the latest BACPAC into a scratch database, check it

In Azure both run as Container Apps Jobs with a managed identity (no passwords): the export reads
the Azure SQL database and writes to the private `backups` Blob container; the drill restores
into a SQL Server that runs next to it in the same job and is gone when the job ends. Locally and
in CI they run against SQL Server with a SQL login and a folder.

The manifest is written after the file, so a manifest means a complete backup. It holds the
file's size and SHA-256, the migration version, every table's row count and the transactions'
total amount; the drill compares the restored database with it and records the result under
`drills/`. Blob lifecycle rules delete backups after 30 days.

Settings (environment):
- SOURCE_SERVER, SOURCE_DATABASE, SOURCE_AUTH (sql or msi), SOURCE_USER, SOURCE_PASSWORD,
  SOURCE_TRUST_CERT (1 for a local SQL Server);
- DRILL_SERVER, DRILL_DATABASE (must end in "restore"), DRILL_AUTH, DRILL_USER, DRILL_PASSWORD,
  DRILL_TRUST_CERT, DRILL_SHUTDOWN (1: stop the scratch SQL Server when done, so the job ends);
- AZURE_CLIENT_ID: the job's managed identity (msi auth and Blob);
- BACKUP_ACCOUNT_URL and BACKUP_CONTAINER (Blob), or BACKUP_DIR (a folder);
- SQLPACKAGE: path of the sqlpackage tool (default: on the PATH).
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

DB_PREFIX = "db/"
DRILL_PREFIX = "drills/"
WAIT_SECONDS = 240


class BackupError(Exception):
    pass


# ---------------------------------------------------------------- connections
@dataclass
class Target:
    server: str
    database: str
    auth: str = "sql"  # sql, or msi (managed identity)
    user: str | None = None
    password: str | None = None
    client_id: str | None = None
    trust_cert: bool = False

    @classmethod
    def from_env(cls, prefix: str, env: Mapping[str, str] = os.environ) -> "Target":
        def get(name: str) -> str | None:
            return env.get(f"{prefix}_{name}") or None

        server, database = get("SERVER"), get("DATABASE")
        if not server or not database:
            raise BackupError(f"Set {prefix}_SERVER and {prefix}_DATABASE.")
        auth = (get("AUTH") or "sql").lower()
        if auth not in ("sql", "msi"):
            raise BackupError(f"{prefix}_AUTH is sql or msi.")
        if auth == "sql" and not (get("USER") and get("PASSWORD")):
            raise BackupError(f"Set {prefix}_USER and {prefix}_PASSWORD for SQL authentication.")
        return cls(
            server=server,
            database=database,
            auth=auth,
            user=get("USER"),
            password=get("PASSWORD"),
            client_id=env.get("AZURE_CLIENT_ID") or None,
            trust_cert=get("TRUST_CERT") == "1",
        )

    def odbc(self, database: str | None = None) -> str:
        """For pyodbc (ODBC Driver 18)."""
        parts = [
            "DRIVER={ODBC Driver 18 for SQL Server}",
            f"SERVER={self.server}",
            f"DATABASE={database or self.database}",
            "Encrypt=yes",
            f"TrustServerCertificate={'yes' if self.trust_cert else 'no'}",
            "Connection Timeout=60",
        ]
        if self.auth == "msi":
            parts.append("Authentication=ActiveDirectoryMsi")
            if self.client_id:
                parts.append(f"UID={self.client_id}")
        else:
            parts += [f"UID={self.user}", "PWD={" + (self.password or "").replace("}", "}}") + "}"]
        return ";".join(parts)

    def sqlclient(self, database: str | None = None) -> str:
        """For sqlpackage (Microsoft.Data.SqlClient)."""
        parts = [
            f"Server={self.server}",
            f"Database={database or self.database}",
            "Encrypt=True",
            f"TrustServerCertificate={self.trust_cert}",
            "Connect Timeout=60",
        ]
        if self.auth == "msi":
            parts.append("Authentication=Active Directory Managed Identity")
            if self.client_id:
                parts.append(f"User Id={self.client_id}")
        else:
            password = (self.password or "").replace('"', '""')
            parts += [f"User ID={self.user}", f'Password="{password}"']
        return ";".join(parts)


def _connect(target: Target, database: str | None = None, autocommit: bool = False) -> Any:
    import pyodbc

    return pyodbc.connect(target.odbc(database), autocommit=autocommit)


def table_counts(target: Target) -> dict[str, int]:
    """Every user table's exact row count, as "schema.table"."""
    with _connect(target) as conn:
        tables = conn.execute(
            "SELECT [s].[name], [t].[name] FROM [sys].[tables] AS [t] "
            "JOIN [sys].[schemas] AS [s] ON [s].[schema_id] = [t].[schema_id] "
            "WHERE [t].[is_ms_shipped] = 0 ORDER BY [s].[name], [t].[name]"
        ).fetchall()
        out = {}
        for schema, name in tables:
            n = conn.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{name}]").fetchone()[0]
            out[f"{schema}.{name}"] = int(n)
        return out


def facts(target: Target) -> dict[str, Any]:
    """What a restore must give back: migration version, row counts, transactions' total."""
    counts = table_counts(target)
    with _connect(target) as conn:
        version = conn.execute("SELECT [version_num] FROM [audit].[alembic_version]").fetchone()
        total = conn.execute("SELECT SUM([amount]) FROM [core].[transaction]").fetchone()[0]
    return {
        "migration": version[0] if version else None,
        "tables": counts,
        "transaction_total": str(Decimal(total or 0).quantize(Decimal("0.0001"))),
    }


def run_sqlpackage(args: list[str]) -> float:
    """Run sqlpackage; returns the seconds it took. Connection strings are never printed."""
    tool = os.environ.get("SQLPACKAGE", "sqlpackage")
    started = time.monotonic()
    done = subprocess.run([tool, *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        tail = (done.stdout + done.stderr)[-2000:]
        raise BackupError(f"sqlpackage {args[0]} failed ({done.returncode}): {tail}")
    return round(time.monotonic() - started, 1)


def wait_ready(target: Target, seconds: int = WAIT_SECONDS) -> None:
    """The scratch SQL Server starts with the job: wait until it answers."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            with _connect(target, "master") as conn:
                conn.execute("SELECT 1").fetchone()
                return
        except Exception as exc:  # pyodbc raises several kinds while the server starts
            if time.monotonic() > deadline:
                raise BackupError(f"The scratch SQL Server didn't answer: {exc}") from exc
            time.sleep(5)


def drop_database(target: Target) -> None:
    if not target.database.lower().endswith("restore"):
        raise BackupError("The drill only replaces a database whose name ends in 'restore'.")
    with _connect(target, "master", autocommit=True) as conn:
        conn.execute(
            f"IF DB_ID(N'{target.database}') IS NOT NULL BEGIN "
            f"ALTER DATABASE [{target.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{target.database}]; END"
        )


def shutdown(target: Target) -> None:
    """Stop the scratch SQL Server so the job's replica can finish."""
    try:
        with _connect(target, "master", autocommit=True) as conn:
            conn.execute("SHUTDOWN WITH NOWAIT")
    except Exception:  # the connection drops as the server stops
        pass


# ---------------------------------------------------------------- storage
class BackupStore(Protocol):
    def upload(self, key: str, path: Path) -> None: ...
    def download(self, key: str, path: Path) -> None: ...
    def put_json(self, key: str, data: dict[str, Any]) -> None: ...
    def get_json(self, key: str) -> dict[str, Any]: ...
    def keys(self, prefix: str) -> list[str]: ...


class LocalBackupStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise BackupError("Invalid backup key.")
        return path

    def upload(self, key: str, path: Path) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())

    def download(self, key: str, path: Path) -> None:
        path.write_bytes(self._path(key).read_bytes())

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2))

    def get_json(self, key: str) -> dict[str, Any]:
        out: dict[str, Any] = json.loads(self._path(key).read_text())
        return out

    def keys(self, prefix: str) -> list[str]:
        base = self._path(prefix.rstrip("/") + "/x").parent
        if not base.is_dir():
            return []
        return sorted(f"{prefix}{p.name}" for p in base.iterdir() if p.is_file())


class BlobBackupStore:  # pragma: no cover - exercised in Azure, not in CI
    def __init__(self, account_url: str, container: str, client_id: str | None = None) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        credential = DefaultAzureCredential(managed_identity_client_id=client_id)
        self.container = BlobServiceClient(account_url, credential=credential).get_container_client(
            container
        )

    def upload(self, key: str, path: Path) -> None:
        with path.open("rb") as f:
            self.container.upload_blob(key, f, overwrite=True, max_concurrency=4)

    def download(self, key: str, path: Path) -> None:
        with path.open("wb") as f:
            self.container.download_blob(key, max_concurrency=4).readinto(f)

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        from azure.storage.blob import ContentSettings

        self.container.upload_blob(
            key,
            json.dumps(data, indent=2).encode(),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )

    def get_json(self, key: str) -> dict[str, Any]:
        out: dict[str, Any] = json.loads(self.container.download_blob(key).readall())
        return out

    def keys(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.container.list_blobs(name_starts_with=prefix))


def store_from_env(env: Mapping[str, str] = os.environ) -> BackupStore:
    if env.get("BACKUP_ACCOUNT_URL"):  # pragma: no cover - Azure
        return BlobBackupStore(
            env["BACKUP_ACCOUNT_URL"],
            env.get("BACKUP_CONTAINER", "backups"),
            env.get("AZURE_CLIENT_ID") or None,
        )
    if env.get("BACKUP_DIR"):
        return LocalBackupStore(env["BACKUP_DIR"])
    raise BackupError("Set BACKUP_ACCOUNT_URL (Azure Blob) or BACKUP_DIR (a folder).")


# ---------------------------------------------------------------- the two jobs
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def export(source: Target, store: BackupStore) -> dict[str, Any]:
    started = _now()
    key = f"{DB_PREFIX}{source.database}-{started:%Y%m%d-%H%M%S}.bacpac"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "export.bacpac"
        seconds = run_sqlpackage(
            [
                "/Action:Export",
                f"/SourceConnectionString:{source.sqlclient()}",
                f"/TargetFile:{path}",
                "/Quiet:True",
            ]
        )
        found = facts(source)
        size, digest = path.stat().st_size, _sha256(path)
        store.upload(key, path)
    manifest = {
        "kind": "backup",
        "file": key,
        "database": source.database,
        "started_at": started.isoformat(),
        "finished_at": _now().isoformat(),
        "seconds": seconds,
        "size": size,
        "sha256": digest,
        **found,
    }
    store.put_json(key.removesuffix(".bacpac") + ".json", manifest)
    return manifest


def latest_backup(store: BackupStore) -> dict[str, Any] | None:
    manifests = [k for k in store.keys(DB_PREFIX) if k.endswith(".json")]
    return store.get_json(manifests[-1]) if manifests else None


def latest_drill(store: BackupStore) -> dict[str, Any] | None:
    drills = [k for k in store.keys(DRILL_PREFIX) if k.endswith(".json")]
    return store.get_json(drills[-1]) if drills else None


def compare(expected: dict[str, Any], got: dict[str, Any]) -> list[str]:
    problems = []
    if expected.get("migration") != got.get("migration"):
        problems.append(f"Migration {got.get('migration')} instead of {expected.get('migration')}.")
    want, have = expected.get("tables", {}), got.get("tables", {})
    for table in sorted(set(want) | set(have)):
        if want.get(table) != have.get(table):
            problems.append(f"{table}: {have.get(table)} rows instead of {want.get(table)}.")
    if expected.get("transaction_total") != got.get("transaction_total"):
        problems.append(
            f"Transactions total {got.get('transaction_total')} instead of "
            f"{expected.get('transaction_total')}."
        )
    return problems


def drill(target: Target, store: BackupStore, stop_server: bool = False) -> dict[str, Any]:
    """Restore the latest backup into the scratch database and check it against its manifest.
    The result is recorded whether it passes or not."""
    started = _now()
    result: dict[str, Any] = {"kind": "drill", "started_at": started.isoformat(), "ok": False}
    try:
        manifest = latest_backup(store)
        if manifest is None:
            raise BackupError("There is no backup to restore yet.")
        result["backup"] = manifest["file"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "restore.bacpac"
            store.download(manifest["file"], path)
            if _sha256(path) != manifest["sha256"]:
                raise BackupError("The backup file doesn't match its manifest's SHA-256.")
            wait_ready(target)
            drop_database(target)
            result["seconds"] = run_sqlpackage(
                [
                    "/Action:Import",
                    f"/SourceFile:{path}",
                    f"/TargetConnectionString:{target.sqlclient()}",
                    "/Quiet:True",
                ]
            )
        got = facts(target)
        result["problems"] = compare(manifest, got)
        result["tables"] = len(got["tables"])
        result["rows"] = sum(got["tables"].values())
        result["ok"] = not result["problems"]
    except BackupError as exc:
        result["problems"] = [str(exc)]
    except Exception as exc:  # anything else (a SQL error, storage): record why, then fail
        # The job's console isn't kept, so the result is where the reason has to be.
        result["problems"] = [f"{type(exc).__name__}: {str(exc)[:500]}"]
    finally:
        result["finished_at"] = _now().isoformat()
        store.put_json(f"{DRILL_PREFIX}drill-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.json", result)
        if stop_server:
            shutdown(target)
    return result


def main(argv: list[str] | None = None, env: Mapping[str, str] = os.environ) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in (["export"], ["drill"]):
        print("usage: python -m app.ops.backup export|drill", file=sys.stderr)
        return 2
    store = store_from_env(env)
    if args == ["export"]:
        m = export(Target.from_env("SOURCE", env), store)
        print(f"backup {m['file']}: {m['size']} bytes, {sum(m['tables'].values())} rows")
        return 0
    r = drill(Target.from_env("DRILL", env), store, stop_server=env.get("DRILL_SHUTDOWN") == "1")
    print(f"drill of {r.get('backup')}: {'ok' if r['ok'] else 'FAILED'}")
    for p in r.get("problems", []):
        print(f"  {p}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
