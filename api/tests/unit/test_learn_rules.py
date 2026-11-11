"""ADR-079: the second time a merchant gets the same category by hand, the rule is saved."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, MerchantRule
from tests.unit.test_line_context import USER, _add, _cat


def _edit(client: TestClient, tid: int, cat: int | None) -> dict[str, object]:
    r = client.patch(f"/api/transactions/{tid}", json={"category_id": cat}, headers=USER)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_second_choice_by_hand_saves_the_rule(client: TestClient, db: Session) -> None:
    a = db.scalars(select(Account).limit(1)).one()
    one = _add(db, a, date(2026, 10, 3), "-7.00", "PANADERIA AMBATO 0041")
    two = _add(db, a, date(2026, 10, 9), "-5.50", "PANADERIA AMBATO 0041")
    three = _add(db, a, date(2026, 10, 20), "-6.10", "PANADERIA AMBATO 0041")
    db.commit()
    bakery, other = _cat(db, "Supermarket"), _cat(db, "Restaurants & Cafés")

    assert _edit(client, one.transaction_id, bakery)["learned"] is None  # once isn't a habit
    got = _edit(client, two.transaction_id, bakery)["learned"]
    assert isinstance(got, dict) and got["lines"] == 1 and "PANADERIA AMBATO" in got["pattern"]
    db.expire_all()
    rule = db.get(MerchantRule, got["rule_id"])
    assert rule is not None and rule.category_id == bakery and rule.match_type == "contains"
    assert three.category_id == bakery and three.category_source == "rule"

    # The rule exists now: nothing more is learned; turned off (Undo), it isn't saved again.
    assert _edit(client, one.transaction_id, bakery)["learned"] is None
    off = client.patch(f"/api/merchant-rules/{got['rule_id']}", json={"is_active": False})
    assert off.status_code == 200
    assert _edit(client, two.transaction_id, other)["learned"] is None
    assert _edit(client, two.transaction_id, bakery)["learned"] is None


def test_nothing_is_learned_from_bare_transfers_or_mixed_choices(
    client: TestClient, db: Session
) -> None:
    a = db.scalars(select(Account).limit(1)).one()
    t1 = _add(db, a, date(2026, 10, 3), "-50.00", "TRANSFERENCIA INTERNET")
    t2 = _add(db, a, date(2026, 10, 9), "-80.00", "TRANSFERENCIA INTERNET")
    m1 = _add(db, a, date(2026, 10, 3), "-9.00", "FARMACIA CRUZ AZUL")
    m2 = _add(db, a, date(2026, 10, 9), "-12.00", "FARMACIA CRUZ AZUL")
    db.commit()
    x, y = _cat(db, "Supermarket"), _cat(db, "Pharmacy")
    _edit(client, t1.transaction_id, x)
    assert _edit(client, t2.transaction_id, x)["learned"] is None  # it names no one
    _edit(client, m1.transaction_id, x)
    assert _edit(client, m2.transaction_id, y)["learned"] is None  # two ways: no rule
    assert (
        db.scalars(select(MerchantRule).where(MerchantRule.pattern.like("%CRUZ%"))).first() is None
    )
