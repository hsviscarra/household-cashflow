from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.cli import import_excel_history as cli
from app.models import Transaction
from tests.fixtures.workbook import build


def test_cli_previews_then_loads(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    book = tmp_path / "Cash Flow.xlsx"
    book.write_bytes(build())

    assert cli.main([str(book)]) == 0
    out = capsys.readouterr().out
    assert "2019-11-01 to 2026-01-01" in out and "Aliquota Ofi 75.35" in out
    assert "typed-in total  <-- not explained" in out
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 0

    assert cli.main([str(book), "--load"]) == 0
    assert "Loaded:" in capsys.readouterr().out
    assert cli.main([str(book), "--load"]) == 1
    assert "already loaded" in capsys.readouterr().err


def test_cli_stops_on_unmapped_rows(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    book = tmp_path / "book.xlsx"
    book.write_bytes(build(extra_income_label="Lottery"))
    assert cli.main([str(book), "--load"]) == 1
    assert "Unmapped rows: Lottery" in capsys.readouterr().out
