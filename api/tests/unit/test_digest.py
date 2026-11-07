"""ADR-038: the weekly digest the Gmail script emails. Synthetic data only."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures.invoices import KEY, factura
from tests.unit.test_bills_api import _gen
from tests.unit.test_invoices import inbox, upload  # noqa: F401
from tests.unit.test_recurring_api import _template
from tests.unit.test_shopping import _add, _cat


def test_the_digest_needs_the_token(client: TestClient) -> None:
    assert client.get("/api/inbox").status_code == 404  # no token set: the inbox is off


def test_an_all_clear_week(inbox: dict[str, str], client: TestClient) -> None:  # noqa: F811
    out = client.get("/api/inbox", params={"today": "2026-11-09"}, headers=inbox)
    assert out.status_code == 200, out.text
    d = out.json()
    assert d["actions"] == 0 and d["subject"] == "Cashflow, week of Nov 09: all clear"
    assert d["summary"] == "Spent $0.00 in November so far."
    assert "Nothing needs you this week." in d["text"] and "Nothing needs you" in d["html"]
    bad = client.get("/api/inbox", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_a_week_with_things_to_do(
    inbox: dict[str, str],  # noqa: F811
    client: TestClient,
    db: Session,
) -> None:
    market = _cat(db, "Supermarket")
    # Usual vet bills around $40, then $180 this week: unusual.
    for d in (date(2026, 8, 3), date(2026, 9, 2), date(2026, 10, 1)):
        _add(db, d, "-40", "VETERINARIA PATITAS", market)
    _add(db, date(2026, 11, 6), "-180", "VETERINARIA PATITAS", market)
    # A line without a category (the Inbox), and October's spending for the comparison.
    _add(db, date(2026, 11, 3), "-25", "TIENDA NUEVA", None)
    _add(db, date(2026, 10, 4), "-100", "SUPERMAXI", market)
    db.commit()
    _template(
        client,
        name="Internet",
        category_id=market.category_id,
        amount="40",
        start_month="2026-11-01",
        due_day=12,
    )
    _gen(client, "2026-11-01")
    upload(client, ("a.xml", factura(key=KEY[:-3] + "901", day="02/11/2026")))

    d = client.get("/api/inbox", params={"today": "2026-11-09"}, headers=inbox).json()
    titles = [s["title"] for s in d["sections"]]
    assert titles[0] == "Needs a category"
    assert d["sections"][0]["items"] == ["1 line from 1 merchant in the Inbox"]
    bills = next(s for s in d["sections"] if s["title"] == "Bills this week")
    assert bills["items"][0].startswith("Internet: $40.00 due Thu Nov 12")
    odd = next(s for s in d["sections"] if s["title"] == "Unusual charges this week")
    assert odd["items"] == ["VETERINARIA PATITAS: $180.00 on Nov 06, usually about $40.00"]
    taxes = next(s for s in d["sections"] if s["title"] == "Gastos personales")
    assert taxes["items"] == ["1 invoice to sort out for 2026"]
    # 180 + 25 against 100 + the $40 vet bill of Oct 1, in the same days of October.
    assert d["summary"] == "Spent $205.00 in November so far, +46% vs the same days of October."
    assert d["subject"] == f"Cashflow, week of Nov 09: {d['actions']} things need you"
    assert 'href="http://testserver/transactions?q=VETERINARIA PATITAS"' in d["html"]
    assert "NEEDS A CATEGORY\n- 1 line from 1 merchant in the Inbox" in d["text"]
    assert d["text"].endswith("Open the app: http://testserver")
