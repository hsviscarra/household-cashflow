"""ADR-081: Claude's SRI category for issuers nobody classified, saved when it is sure."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GpIssuerRule, Invoice, InvoiceLine
from app.services import gastos, gastos_suggest


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()


def _inv(db: Session, n: int, ruc: str, name: str, product: str, amount: str) -> Invoice:
    inv = Invoice(
        access_key=f"{900 + n:049d}",
        issuer_ruc=ruc,
        issuer_name=name,
        number=f"001-001-{900 + n:09d}",
        issue_date=date(2026, 10, n),
        subtotal=Decimal(amount),
        tax=Decimal(0),
        total=Decimal(amount),
        received_by="test",
    )
    db.add(inv)
    db.flush()
    db.add(
        InvoiceLine(
            invoice_id=inv.invoice_id,
            line_no=1,
            description=product,
            quantity=Decimal(1),
            unit_price=Decimal(amount),
            discount=Decimal(0),
            subtotal=Decimal(amount),
            tax=Decimal(0),
            total=Decimal(amount),
            product_key=product.casefold(),
        )
    )
    return inv


def test_sure_answers_become_issuer_rules(
    client: TestClient, db: Session, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    school = _inv(db, 1, "1791376323001", "FUNDACION EDUCACIONAL", "PENSION OCTUBRE", "719.00")
    _inv(db, 2, "1790000000001", "IMPORTADORA VARIOS", "ARTICULO", "40.00")
    known = _inv(db, 3, "1790000000002", "CLINICA", "CONSULTA", "60.00")
    db.add(GpIssuerRule(issuer_ruc=known.issuer_ruc, gp_category="salud", created_by="hernan"))
    db.commit()
    sent: list[list[gastos_suggest.Asked]] = []

    def fake(asked: list[gastos_suggest.Asked]) -> list[gastos_suggest.Answer]:
        sent.append(asked)
        return [
            gastos_suggest.Answer("1791376323001", "educacion", Decimal("0.97")),
            gastos_suggest.Answer("1790000000001", "none", Decimal("0.55")),
        ]

    monkeypatch.setattr(gastos_suggest, "call_claude", fake)
    done = gastos_suggest.autopilot(db, 2026)
    assert (done.asked, done.saved) == (2, 1)
    # Largest first; the clinic already has a person's rule and isn't asked about.
    assert [a.name for a in sent[0]] == ["FUNDACION EDUCACIONAL", "IMPORTADORA VARIOS"]
    assert sent[0][0].products == ["PENSION OCTUBRE"]
    rule = db.scalars(
        select(GpIssuerRule).where(GpIssuerRule.issuer_ruc == school.issuer_ruc)
    ).one()
    assert (rule.gp_category, rule.created_by) == ("educacion", "claude (automatic)")
    by = {r.invoice_id: r for r in gastos.rows(db, 2026)}
    assert (by[school.invoice_id].category, by[school.invoice_id].category_source) == (
        "educacion",
        "claude",
    )
    assert by[known.invoice_id].category_source == "issuer"
    # Nothing left that Claude is sure about: the unsure one keeps waiting, and is asked again.
    assert gastos_suggest.autopilot(db, 2026).saved == 0


def test_a_failure_leaves_everything_waiting(
    db: Session, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inv(db, 4, "1790000000003", "ALGO", "COSA", "10.00")
    db.commit()

    def broken(_asked: list[gastos_suggest.Asked]) -> list[gastos_suggest.Answer]:
        raise RuntimeError("down")

    monkeypatch.setattr(gastos_suggest, "call_claude", broken)
    assert gastos_suggest.autopilot(db, 2026).saved == 0
    assert db.scalars(select(GpIssuerRule)).first() is None


def test_off_without_a_key(db: Session) -> None:
    assert gastos_suggest.autopilot(db, 2026).asked == 0
