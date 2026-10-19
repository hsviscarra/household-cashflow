import pytest

from app.config import get_settings
from app.db import ensure_database


def test_skipped_outside_local(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "azure")
    get_settings.cache_clear()
    try:
        ensure_database.main()
        assert "skipped" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()


def test_rejects_unsafe_database_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "mssql+pyodbc://sa:x@localhost/bad;name")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            ensure_database.main()
    finally:
        get_settings.cache_clear()
