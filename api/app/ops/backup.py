"""Nightly database export and monthly restore drill (F17, ADR-016).

    python -m app.ops.backup export   # BACPAC of the database, then its manifest
    python -m app.ops.backup drill    # restore the latest BACPAC into a scratch database, check it
    python -m app.ops.backup copy     # export SOURCE and import it into the empty TARGET (ADR-107)

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
- TARGET_SERVER, TARGET_DATABASE, TARGET_AUTH, TARGET_USER, TARGET_PASSWORD, TARGET_TRUST_CERT,
  TARGET_CREATE (1: the import may create the database: the local SQL Server only), for `copy`;
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
    """The backup or the drill can't go on; the message says why."""

    pass


# ---------------------------------------------------------------- connections
@dataclass
class Target:
    """A database to connect to: server, name and how to sign in."""

    server: str
    database: str
    auth: str = "sql"  # sql, or msi (managed identity)
    user: str | None = None
    password: str | None = None
    client_id: str | None = None
    trust_cert: bool = False

    @classmethod
    def from_env(cls, prefix: str, env: Mapping[str, str] = os.environ) -> "Target":
        """A database to connect to, from PREFIX_SERVER, PREFIX_DATABASE and the rest in the
        environment."""

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


def wait_ready(target: Target, seconds: int = WAIT_SECONDS, database: str = "master") -> None:
    """Wait until a server answers: the drill's scratch SQL Server starts with the job, and a
    paused Azure database resumes in about a minute once something logs in to it (logging in
    to `master` doesn't wake it, so `wake` names the database itself)."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            with _connect(target, database) as conn:
                conn.execute("SELECT 1").fetchone()
                return
        # pyodbc (imported only where the job runs) raises several kinds while the server starts.
        except Exception as exc:
            if time.monotonic() > deadline:
                raise BackupError(f"{target.server} didn't answer: {exc}") from exc
            time.sleep(5)


def wake(target: Target) -> None:
    """Resume a paused serverless database before sqlpackage needs it (sqlpackage gives up on
    "not currently available")."""
    wait_ready(target, database=target.database)


def drop_database(target: Target) -> None:
    """Drop the drill's scratch database; refuses any database whose name doesn't end in
    'restore'."""
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
    # pyodbc (imported only where the job runs) raises its own Error as the server stops and
    # drops the connection; that is the expected end of this call, not a failure.
    except Exception:  # noqa: BLE001, S110 - see above: the dropped connection is the success
        pass


# ---------------------------------------------------------------- storage
class BackupStore(Protocol):
    """Where backups and their manifests are kept."""

    def upload(self, key: str, path: Path) -> None:
        """Store the file at `path` under `key`."""
        ...

    def download(self, key: str, path: Path) -> None:
        """Write what is stored under `key` to `path`."""
        ...

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        """Store a JSON document under `key`."""
        ...

    def get_json(self, key: str) -> dict[str, Any]:
        """The JSON document stored under `key`."""
        ...

    def keys(self, prefix: str) -> list[str]:
        """Every key that starts with `prefix`, in order."""
        ...


class LocalBackupStore:
    """Backups in a local folder (local runs and tests)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise BackupError("Invalid backup key.")
        return path

    def upload(self, key: str, path: Path) -> None:
        """Copy the file into the backups folder."""
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())

    def download(self, key: str, path: Path) -> None:
        """Copy the stored file to `path`."""
        path.write_bytes(self._path(key).read_bytes())

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        """Write the document as a JSON file."""
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2))

    def get_json(self, key: str) -> dict[str, Any]:
        """Read the JSON file stored under `key`."""
        out: dict[str, Any] = json.loads(self._path(key).read_text())
        return out

    def keys(self, prefix: str) -> list[str]:
        """The files under `prefix`, in order."""
        base = self._path(prefix.rstrip("/") + "/x").parent
        if not base.is_dir():
            return []
        return sorted(f"{prefix}{p.name}" for p in base.iterdir() if p.is_file())


class BlobBackupStore:  # pragma: no cover - exercised in Azure, not in CI
    """Backups in an Azure Blob container, signed in with the managed identity."""

    def __init__(self, account_url: str, container: str, client_id: str | None = None) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        credential = DefaultAzureCredential(managed_identity_client_id=client_id)
        self.container = BlobServiceClient(account_url, credential=credential).get_container_client(
            container
        )

    def upload(self, key: str, path: Path) -> None:
        """Upload the file to the container, replacing any blob of that name."""
        with path.open("rb") as f:
            self.container.upload_blob(key, f, overwrite=True, max_concurrency=4)

    def download(self, key: str, path: Path) -> None:
        """Download the blob to `path`."""
        with path.open("wb") as f:
            self.container.download_blob(key, max_concurrency=4).readinto(f)

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        """Upload the document as a JSON blob."""
        from azure.storage.blob import ContentSettings

        self.container.upload_blob(
            key,
            json.dumps(data, indent=2).encode(),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )

    def get_json(self, key: str) -> dict[str, Any]:
        """Download and read the JSON blob."""
        out: dict[str, Any] = json.loads(self.container.download_blob(key).readall())
        return out

    def keys(self, prefix: str) -> list[str]:
        """The blobs whose names start with `prefix`, in order."""
        return sorted(b.name for b in self.container.list_blobs(name_starts_with=prefix))


def store_from_env(env: Mapping[str, str] = os.environ) -> BackupStore:
    """Blob storage when BACKUP_ACCOUNT_URL is set, else a local folder."""
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
    """Export the database to a .bacpac, store it with a manifest (row counts, migration, totals)
    and return the manifest."""
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
    """The newest backup's manifest, or None when there is no backup."""
    manifests = [k for k in store.keys(DB_PREFIX) if k.endswith(".json")]
    return store.get_json(manifests[-1]) if manifests else None


def latest_drill(store: BackupStore) -> dict[str, Any] | None:
    """The newest restore drill's result, or None."""
    drills = [k for k in store.keys(DRILL_PREFIX) if k.endswith(".json")]
    return store.get_json(drills[-1]) if drills else None


def compare(expected: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """What differs between what a backup said it held and what the restore holds; empty when
    equal."""
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


def _import_latest(target: Target, store: BackupStore) -> tuple[dict[str, Any], float]:
    """Download the newest backup, check it against its manifest's SHA-256 and import it into
    `target`. Returns the manifest and the seconds the import took."""
    manifest = latest_backup(store)
    if manifest is None:
        raise BackupError("There is no backup to restore yet.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "restore.bacpac"
        store.download(manifest["file"], path)
        if _sha256(path) != manifest["sha256"]:
            raise BackupError("The backup file doesn't match its manifest's SHA-256.")
        seconds = run_sqlpackage(
            [
                "/Action:Import",
                f"/SourceFile:{path}",
                f"/TargetConnectionString:{target.sqlclient()}",
                "/Quiet:True",
            ]
        )
    return manifest, seconds


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
        wait_ready(target)
        drop_database(target)
        manifest, result["seconds"] = _import_latest(target, store)
        got = facts(target)
        result["problems"] = compare(manifest, got)
        result["tables"] = len(got["tables"])
        result["rows"] = sum(got["tables"].values())
        result["ok"] = not result["problems"]
    except BackupError as exc:
        result["problems"] = [str(exc)]
    except Exception as exc:  # noqa: BLE001 - a drill must always leave a result behind
        # The job's console isn't kept, so the result is where the reason has to be.
        result["problems"] = [f"{type(exc).__name__}: {str(exc)[:500]}"]
    finally:
        result["finished_at"] = _now().isoformat()
        store.put_json(f"{DRILL_PREFIX}drill-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.json", result)
        if stop_server:
            shutdown(target)
    return result


# ------------------------------------------------- moving the data (ADR-107)
def prepare_target(target: Target, allow_create: bool) -> None:
    """A copy only writes into an empty database. On Azure it must already exist (created with
    the free offer: a database sqlpackage creates there is billed); on the local SQL Server it
    may be created by the import, which then needs contained users allowed (the read-only MCP
    user is one on Azure)."""
    with _connect(target, "master", autocommit=True) as conn:
        exists = conn.execute("SELECT DB_ID(?)", target.database).fetchone()[0] is not None
        if not exists and allow_create:
            conn.execute("EXEC sp_configure 'contained database authentication', 1; RECONFIGURE;")
    if not exists:
        if not allow_create:
            raise BackupError(f"Create the database {target.database} first, with the free offer.")
        return
    wake(target)
    with _connect(target) as conn:
        tables = conn.execute(
            "SELECT COUNT(*) FROM [sys].[tables] WHERE [is_ms_shipped] = 0"
        ).fetchone()[0]
    if tables:
        raise BackupError(
            f"{target.database} already holds {tables} tables; a copy only writes into an empty "
            "database."
        )


def copy(
    source: Target, target: Target, store: BackupStore, allow_create: bool = False
) -> dict[str, Any]:
    """Move the whole database from `source` to `target`: export a backup with its manifest,
    import it into the empty target and compare the target with the manifest. Used to park the
    Azure database on a laptop and to bring it back. The backup stays in `store` either way."""
    wake(source)
    prepare_target(target, allow_create)
    manifest = export(source, store)
    _, seconds = _import_latest(target, store)
    got = facts(target)
    problems = compare(manifest, got)
    return {
        "kind": "copy",
        "backup": manifest["file"],
        "from": source.database,
        "to": target.database,
        "seconds": seconds,
        "tables": len(got["tables"]),
        "rows": sum(got["tables"].values()),
        "transaction_total": got["transaction_total"],
        "problems": problems,
        "ok": not problems,
    }


COMMANDS = ("export", "drill", "copy")


def main(argv: list[str] | None = None, env: Mapping[str, str] = os.environ) -> int:
    """The jobs' and the park script's entry point: `export`, `drill` or `copy`; returns the
    exit code."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in COMMANDS:
        print(f"usage: python -m app.ops.backup {'|'.join(COMMANDS)}", file=sys.stderr)
        return 2
    store = store_from_env(env)
    if args == ["export"]:
        m = export(Target.from_env("SOURCE", env), store)
        print(f"backup {m['file']}: {m['size']} bytes, {sum(m['tables'].values())} rows")
        return 0
    if args == ["copy"]:
        try:
            r = copy(
                Target.from_env("SOURCE", env),
                Target.from_env("TARGET", env),
                store,
                allow_create=env.get("TARGET_CREATE") == "1",
            )
        except BackupError as exc:
            print(f"copy FAILED: {exc}", file=sys.stderr)
            return 1
        print(
            f"copy {r['from']} -> {r['to']}: {'ok' if r['ok'] else 'FAILED'}, "
            f"{r['tables']} tables, {r['rows']} rows, transactions total {r['transaction_total']}"
        )
        for p in r["problems"]:
            print(f"  {p}")
        return 0 if r["ok"] else 1
    r = drill(Target.from_env("DRILL", env), store, stop_server=env.get("DRILL_SHUTDOWN") == "1")
    print(f"drill of {r.get('backup')}: {'ok' if r['ok'] else 'FAILED'}")
    for p in r.get("problems", []):
        print(f"  {p}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
