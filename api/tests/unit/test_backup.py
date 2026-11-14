"""F17: the backup runner's orchestration, with sqlpackage and SQL Server faked. The real export
and restore run in the integration tests against SQL Server."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.ops import backup
from app.ops.backup import BackupError, LocalBackupStore, Target

FACTS = {
    "migration": "0018",
    "tables": {"core.transaction": 10, "core.account": 3},
    "transaction_total": "-123.4500",
}
SOURCE = Target("db.example.net", "cashflow", "msi", client_id="abc")
SCRATCH = Target("localhost", "cashflow_restore", "sql", "sa", 'p}w;d"', trust_cert=True)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"sqlpackage": [], "facts": [dict(FACTS)], "dropped": [], "stopped": 0}

    def run(args: list[str]) -> float:
        calls["sqlpackage"].append(args)
        if args[0] == "/Action:Export":
            target = next(a for a in args if a.startswith("/TargetFile:")).split(":", 1)[1]
            Path(target).write_bytes(b"PK fake bacpac")
        return 1.5

    def facts(target: Target) -> dict[str, Any]:
        f: dict[str, Any] = calls["facts"][-1]
        return f

    monkeypatch.setattr(backup, "run_sqlpackage", run)
    monkeypatch.setattr(backup, "facts", facts)
    monkeypatch.setattr(backup, "wait_ready", lambda t, seconds=0: None)
    monkeypatch.setattr(backup, "drop_database", lambda t: calls["dropped"].append(t.database))

    def stop(t: Target) -> None:
        calls["stopped"] += 1

    monkeypatch.setattr(backup, "shutdown", stop)
    return calls


def test_connection_strings() -> None:
    assert SOURCE.odbc() == (
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=db.example.net;DATABASE=cashflow;"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
        "Authentication=ActiveDirectoryMsi;UID=abc"
    )
    assert SOURCE.sqlclient() == (
        "Server=db.example.net;Database=cashflow;Encrypt=True;TrustServerCertificate=False;"
        "Connect Timeout=60;Authentication=Active Directory Managed Identity;User Id=abc"
    )
    assert SCRATCH.odbc("master").endswith(
        "DATABASE=master;Encrypt=yes;TrustServerCertificate=yes;"
        'Connection Timeout=60;UID=sa;PWD={p}}w;d"}'
    )
    assert SCRATCH.sqlclient().endswith('User ID=sa;Password="p}w;d"""')


def test_target_from_env() -> None:
    env = {
        "DRILL_SERVER": "localhost",
        "DRILL_DATABASE": "cashflow_restore",
        "DRILL_USER": "sa",
        "DRILL_PASSWORD": "x",
        "DRILL_TRUST_CERT": "1",
    }
    t = Target.from_env("DRILL", env)
    assert (t.auth, t.trust_cert, t.user) == ("sql", True, "sa")
    msi = Target.from_env(
        "SOURCE",
        {
            "SOURCE_SERVER": "s",
            "SOURCE_DATABASE": "d",
            "SOURCE_AUTH": "MSI",
            "AZURE_CLIENT_ID": "c",
        },
    )
    assert (msi.auth, msi.client_id) == ("msi", "c")
    with pytest.raises(BackupError, match="SOURCE_SERVER"):
        Target.from_env("SOURCE", {})
    with pytest.raises(BackupError, match="sql or msi"):
        Target.from_env(
            "SOURCE", {"SOURCE_SERVER": "s", "SOURCE_DATABASE": "d", "SOURCE_AUTH": "x"}
        )
    with pytest.raises(BackupError, match="SOURCE_USER"):
        Target.from_env("SOURCE", {"SOURCE_SERVER": "s", "SOURCE_DATABASE": "d"})


def test_local_store(tmp_path: Path) -> None:
    store = LocalBackupStore(tmp_path)
    assert store.keys("db/") == []
    src = tmp_path / "x.bin"
    src.write_bytes(b"abc")
    store.upload("db/a.bacpac", src)
    store.put_json("db/a.json", {"ok": 1})
    assert store.keys("db/") == ["db/a.bacpac", "db/a.json"]
    assert store.get_json("db/a.json") == {"ok": 1}
    out = tmp_path / "y.bin"
    store.download("db/a.bacpac", out)
    assert out.read_bytes() == b"abc"
    with pytest.raises(BackupError, match="Invalid"):
        store.get_json("../../etc/passwd")
    with pytest.raises(BackupError, match="BACKUP_ACCOUNT_URL"):
        backup.store_from_env({})
    assert isinstance(backup.store_from_env({"BACKUP_DIR": str(tmp_path)}), LocalBackupStore)


def test_export_then_drill(fake: dict[str, Any], tmp_path: Path) -> None:
    store = LocalBackupStore(tmp_path)
    assert backup.latest_backup(store) is None
    m = backup.export(SOURCE, store)
    assert m["file"].startswith("db/cashflow-") and m["file"].endswith(".bacpac")
    assert (m["size"], m["migration"], m["tables"]) == (14, "0018", FACTS["tables"])
    assert len(m["sha256"]) == 64 and m["seconds"] == 1.5
    args = fake["sqlpackage"][0]
    assert args[0] == "/Action:Export" and "Managed Identity" in args[1]
    # The manifest is written last and names the file.
    assert backup.latest_backup(store) == m
    assert store.keys("db/") == [m["file"], m["file"].replace(".bacpac", ".json")]

    r = backup.drill(SCRATCH, store, stop_server=True)
    assert r["ok"] and r["problems"] == [] and r["backup"] == m["file"]
    assert (r["tables"], r["rows"]) == (2, 13)
    assert fake["dropped"] == ["cashflow_restore"] and fake["stopped"] == 1
    assert fake["sqlpackage"][1][0] == "/Action:Import"
    assert backup.latest_drill(store) == r


def test_drill_reports_differences(fake: dict[str, Any], tmp_path: Path) -> None:
    store = LocalBackupStore(tmp_path)
    backup.export(SOURCE, store)
    fake["facts"].append(
        {
            "migration": "0017",
            "tables": {"core.transaction": 9, "core.extra": 1},
            "transaction_total": "0.0000",
        }
    )
    r = backup.drill(SCRATCH, store)
    assert not r["ok"] and fake["stopped"] == 0
    assert r["problems"] == [
        "Migration 0017 instead of 0018.",
        "core.account: None rows instead of 3.",
        "core.extra: 1 rows instead of None.",
        "core.transaction: 9 rows instead of 10.",
        "Transactions total 0.0000 instead of -123.4500.",
    ]


def test_drill_failures_are_recorded(fake: dict[str, Any], tmp_path: Path) -> None:
    store = LocalBackupStore(tmp_path)
    r = backup.drill(SCRATCH, store)
    assert r["problems"] == ["There is no backup to restore yet."] and not r["ok"]
    m = backup.export(SOURCE, store)
    (tmp_path / m["file"]).write_bytes(b"tampered")
    r = backup.drill(SCRATCH, store)
    assert r["problems"] == ["The backup file doesn't match its manifest's SHA-256."]
    assert len(store.keys("drills/")) == 2


def test_drill_refuses_a_real_database(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(BackupError, match="ends in 'restore'"):
        backup.drop_database(Target("s", "cashflow", "sql", "u", "p"))


def test_main(fake: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env = {
        "BACKUP_DIR": str(tmp_path),
        "SOURCE_SERVER": "s",
        "SOURCE_DATABASE": "cashflow",
        "SOURCE_USER": "u",
        "SOURCE_PASSWORD": "p",
        "DRILL_SERVER": "localhost",
        "DRILL_DATABASE": "cashflow_restore",
        "DRILL_USER": "sa",
        "DRILL_PASSWORD": "p",
        "DRILL_SHUTDOWN": "1",
    }
    assert backup.main(["nope"], env) == 2
    assert backup.main(["export"], env) == 0
    assert backup.main(["drill"], env) == 0
    assert fake["stopped"] == 1
    fake["facts"].append({**FACTS, "migration": "0001"})
    assert backup.main(["drill"], env) == 1
    out = capsys.readouterr().out
    assert "backup db/cashflow-" in out and "drill of db/cashflow-" in out and "FAILED" in out
    assert "Migration 0001 instead of 0018." in out
    drills = sorted((tmp_path / "drills").iterdir())
    assert json.loads(drills[-1].read_text())["ok"] is False


def test_run_sqlpackage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "sqlpackage"
    script.write_text('#!/bin/sh\necho "args: $1"\n[ "$1" = "/Action:Export" ] || exit 3\n')
    script.chmod(0o755)
    monkeypatch.setenv("SQLPACKAGE", str(script))
    assert backup.run_sqlpackage(["/Action:Export"]) >= 0
    with pytest.raises(BackupError, match=r"sqlpackage /Action:Import failed \(3\): args"):
        backup.run_sqlpackage(["/Action:Import"])


# ---------------------------------------------------------------- status on Data Status
def test_backup_status(tmp_path: Path, client: Any) -> None:
    from datetime import UTC, datetime

    from app.main import create_app
    from app.services import backups

    store = LocalBackupStore(tmp_path)
    now = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    s = backups.status(store, now)
    assert (s.where, s.backup, s.drill, s.backup_overdue, s.drill_overdue) == (
        "local",
        None,
        None,
        True,
        True,
    )
    store.put_json(
        "db/cashflow-20261028-081700.json",
        {
            "file": "db/cashflow-20261028-081700.bacpac",
            "finished_at": "2026-10-28T08:18:30+00:00",
            "size": 2048,
            "migration": "0018",
            "transaction_total": "-1.0000",
            "seconds": 40.0,
            "tables": {"core.transaction": 7, "core.account": 2},
            "sha256": "x",
        },
    )
    store.put_json(
        "drills/drill-20261002-091700-ab12.json",
        {"ok": True, "finished_at": "2026-10-02T09:30:00+00:00", "problems": []},
    )
    s = backups.status(store, now)
    assert s.backup is not None and s.backup["rows"] == 9 and "sha256" not in s.backup
    assert not s.backup_overdue and not s.drill_overdue
    later = datetime(2026, 11, 20, tzinfo=UTC)
    assert backups.status(store, later).backup_overdue
    assert backups.status(store, later).drill_overdue
    store.put_json(
        "drills/drill-20261028-100000-cd34.json",
        {"ok": False, "finished_at": "2026-10-28T10:00:00+00:00", "problems": ["x"]},
    )
    assert backups.status(store, now).drill_overdue  # a failed drill needs attention

    class Broken(LocalBackupStore):
        def keys(self, prefix: str) -> list[str]:
            raise OSError("no route")

    bad = backups.status(Broken(tmp_path), now)
    assert bad.error == "Backups can't be read: no route" and bad.backup_overdue

    from fastapi.testclient import TestClient

    app = create_app()
    app.dependency_overrides[backups.get_backup_store] = lambda: store
    got = TestClient(app).get("/api/backups").json()
    assert got["backup"]["file"] == "db/cashflow-20261028-081700.bacpac"
    assert got["drill"]["ok"] is False and got["where"] == "local"


def test_drill_records_unexpected_errors(fake: dict[str, Any], tmp_path: Path) -> None:
    store = LocalBackupStore(tmp_path)
    backup.export(SOURCE, store)

    def broken(t: Target) -> None:
        raise RuntimeError("Login failed for user 'sa'.")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(backup, "drop_database", broken)
        r = backup.drill(SCRATCH, store, stop_server=True)
    assert r["problems"] == ["RuntimeError: Login failed for user 'sa'."] and not r["ok"]
    assert fake["stopped"] == 1  # the scratch server is still stopped
    assert backup.latest_drill(store) == r


LAPTOP = Target("sqlserver,1433", "cashflow", "sql", "sa", "pw", trust_cert=True)


class _Conn:
    """A pyodbc connection that answers DB_ID and the table count, and records what ran."""

    def __init__(self, ran: list[str], exists: bool, tables: int) -> None:
        self.ran, self.exists, self.tables = ran, exists, tables

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, *params: object) -> "_Conn":
        self.ran.append(sql)
        self.row = (
            (1 if self.exists else None,) if sql.startswith("SELECT DB_ID") else (self.tables,)
        )
        return self

    def fetchone(self) -> tuple[object, ...]:
        return self.row


def _db(monkeypatch: pytest.MonkeyPatch, exists: bool, tables: int = 0) -> list[str]:
    ran: list[str] = []
    monkeypatch.setattr(
        backup, "_connect", lambda t, database=None, autocommit=False: _Conn(ran, exists, tables)
    )
    return ran


def test_copy_moves_the_database_and_checks_it(
    fake: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-107: parking exports Azure's database and imports it into the laptop's SQL Server,
    which may create it there; the copy is checked against the backup's manifest."""
    ran = _db(monkeypatch, exists=False)
    r = backup.copy(SOURCE, LAPTOP, LocalBackupStore(tmp_path), allow_create=True)
    assert r["ok"] and r["problems"] == [] and (r["from"], r["to"]) == ("cashflow", "cashflow")
    assert (r["tables"], r["rows"], r["transaction_total"]) == (2, 13, "-123.4500")
    assert [a[0] for a in fake["sqlpackage"]] == ["/Action:Export", "/Action:Import"]
    assert any("contained database authentication" in s for s in ran)
    assert backup.latest_backup(LocalBackupStore(tmp_path))["file"] == r["backup"]


def test_copy_reports_a_target_that_differs(
    fake: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _db(monkeypatch, exists=True)
    real = backup.export

    def export(source: Target, store: Any) -> dict[str, Any]:
        m = real(source, store)
        fake["facts"].append({**FACTS, "tables": {"core.transaction": 9, "core.account": 3}})
        return m

    monkeypatch.setattr(backup, "export", export)
    r = backup.copy(SOURCE, LAPTOP, LocalBackupStore(tmp_path))
    assert not r["ok"] and r["problems"] == ["core.transaction: 9 rows instead of 10."]


def test_copy_only_writes_into_an_empty_database(
    fake: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is exported or imported when the target isn't empty, or doesn't exist on Azure
    (a database sqlpackage creates there isn't on the free offer)."""
    _db(monkeypatch, exists=True, tables=40)
    with pytest.raises(BackupError, match="already holds 40 tables"):
        backup.copy(LAPTOP, SOURCE, LocalBackupStore(tmp_path))
    ran = _db(monkeypatch, exists=False)
    with pytest.raises(BackupError, match="Create the database cashflow first"):
        backup.copy(LAPTOP, SOURCE, LocalBackupStore(tmp_path))
    assert fake["sqlpackage"] == [] and not any("sp_configure" in s for s in ran)


def test_main_copy(
    fake: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        "BACKUP_DIR": str(tmp_path),
        "SOURCE_SERVER": "db.example.net",
        "SOURCE_DATABASE": "cashflow",
        "SOURCE_USER": "admin",
        "SOURCE_PASSWORD": "x",
        "TARGET_SERVER": "sqlserver,1433",
        "TARGET_DATABASE": "cashflow",
        "TARGET_USER": "sa",
        "TARGET_PASSWORD": "y",
        "TARGET_CREATE": "1",
    }
    _db(monkeypatch, exists=False)
    assert backup.main(["copy"], env) == 0
    assert "copy cashflow -> cashflow: ok, 2 tables, 13 rows" in capsys.readouterr().out
    _db(monkeypatch, exists=True, tables=3)
    assert backup.main(["copy"], env) == 1
    assert "copy FAILED: cashflow already holds 3 tables" in capsys.readouterr().err
    assert backup.main(["restore"], env) == 2
