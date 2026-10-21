from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion import ocr
from app.models import ImportBatch, LoadLog, RawLine, Transaction
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _upload(client: TestClient, name: str, data: bytes) -> dict:  # type: ignore[type-arg]
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    return resp.json()[0]["statement"]  # type: ignore[no-any-return]


def test_read_preview_approve_and_list(client: TestClient, db: Session) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    assert st["can_read"] is True and st["batch"] is None

    resp = client.post(f"/api/statements/{st['statement_file_id']}/read", headers=USER)
    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["status"] == "preview" and b["tieout_ok"] is True
    assert all(c["ok"] for c in b["checks"])
    assert (b["new_lines"], b["duplicate_lines"], b["uncategorized"]) == (11, 0, 1)
    assert b["statement"]["batch"]["status"] == "preview"

    lines = {ln["description"]: ln for ln in b["lines"]}
    uber = lines["UBER EATS SAN JOSE"]
    assert (uber["category_path"], uber["merchant"], uber["person"]) == (
        "Dining / Food Delivery",
        "UBER EATS",
        "Lauren",
    )
    assert uber["country"] == "US"
    assert lines["DL RAPPI ECUADOR Guayaquil"]["country"] == "EC"
    assert lines["CAPITAL ONE MOBILE PYMT"]["type"] == "transfer"
    assert lines["INTEREST CHARGE ON PURCHASES"]["category_path"] == (
        "Financial Costs / Credit Card Interest"
    )
    refund = lines["AMAZON MKTPL*REFUND Amzn.com/bill WA"]
    assert (refund["type"], refund["category_path"]) == ("refund", "Shopping / Amazon")
    assert lines["NEW MERCHANT XYZ MIAMI FL"]["category_path"] is None
    needs = next(c for c in b["by_category"] if c["category_path"] == "Needs a category")
    assert Decimal(needs["amount"]) == Decimal("-40")

    listed = client.get("/api/statements").json()[0]
    assert listed["batch"]["batch_id"] == b["batch_id"]

    ok = client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    assert ok.json() == {"batch_id": b["batch_id"], "loaded": 11, "skipped_duplicates": 0}
    assert client.post(f"/api/batches/{b['batch_id']}/approve").status_code == 409
    assert client.post(f"/api/statements/{st['statement_file_id']}/read").status_code == 409

    log = db.scalars(select(LoadLog).where(LoadLog.source == "statement")).one()
    assert log.rows_loaded == 11 and log.loaded_by == "hernan@example.com"

    sept = client.get("/api/transactions", params={"month": "2026-09-15"}).json()
    assert len(sept) == 9 and all(t["source"] == "statement" for t in sept)
    assert sept[0]["account_name"] == "Capital One Venture"
    octo = client.get("/api/transactions", params={"month": "2026-10-01", "source": "statement"})
    assert {t["description"] for t in octo.json()} == {
        "NEW MERCHANT XYZ MIAMI FL",
        "INTEREST CHARGE ON PURCHASES",
    }
    acct = sept[0]["account_id"]
    assert len(client.get("/api/transactions", params={"account_id": acct}).json()) == 11

    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    # September spending: card purchases less the refund; the card payment is a transfer.
    assert Decimal(monthly["2026-09-01"]["expenses"]) == Decimal("256.75")
    assert Decimal(monthly["2026-10-01"]["expenses"]) == Decimal("50")


def test_identical_lines_load_once_each_and_reloads_are_duplicates(
    client: TestClient, db: Session
) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve")
    assert (
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.description_raw == "UBER EATS SAN JOSE")
        )
        == 2
    )

    # The bank re-issues the same statement as a different file: every line is a duplicate.
    again = _upload(client, "co-again.pdf", s.capitalone_full(extra_lines=[""]) + b"\n")
    b2 = client.post(f"/api/statements/{again['statement_file_id']}/read").json()
    assert (b2["new_lines"], b2["duplicate_lines"]) == (0, 11)
    res = client.post(f"/api/batches/{b2['batch_id']}/approve").json()
    assert (res["loaded"], res["skipped_duplicates"]) == (0, 11)


def test_rereading_a_preview_replaces_it_and_discard(client: TestClient, db: Session) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    sid = st["statement_file_id"]
    client.post(f"/api/statements/{sid}/read")
    second = client.post(f"/api/statements/{sid}/read").json()
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 1
    assert db.scalar(select(func.count()).select_from(RawLine)) == 11

    gone = client.post(f"/api/batches/{second['batch_id']}/reject", headers=USER).json()
    assert gone["status"] == "rejected" and gone["decided_by"] == "hernan@example.com"
    assert client.post(f"/api/batches/{second['batch_id']}/reject").status_code == 409
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_statement_that_does_not_tie_out_cannot_load(client: TestClient) -> None:
    st = _upload(client, "bad.pdf", s.capitalone_full(printed_total_delta="5.00"))
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is False
    bad = next(c for c in b["checks"] if not c["ok"])
    assert Decimal(bad["expected"]) - Decimal(bad["actual"]) == Decimal("5")
    resp = client.post(f"/api/batches/{b['batch_id']}/approve")
    assert resp.status_code == 409 and "tie out" in resp.json()["detail"]


def test_continuity_with_the_previous_statement(client: TestClient) -> None:
    aug = _upload(
        client,
        "aug.pdf",
        s.capitalone_full(
            period=("Aug 04, 2026", "Sep 03, 2026"),
            previous="900.00",
            payment="100.00",
            interest="0.00",
            lauren=[("Aug 10", "Aug 11", "UBER EATS SAN JOSE", "200.00")],
            hernan=[],
            payment_dates="Aug 20 Aug 21",
        ),
    )
    client.post(f"/api/statements/{aug['statement_file_id']}/read")
    sep = _upload(client, "sep.pdf", s.capitalone_full())  # opens at 1,000.00 = Aug closing
    b = client.post(f"/api/statements/{sep['statement_file_id']}/read").json()
    cont = b["checks"][-1]
    assert cont["name"].startswith("Opening balance = closing balance of the Sep 03, 2026")
    assert cont["ok"] is True

    gap = _upload(
        client,
        "gap.pdf",
        s.capitalone_full(
            previous="1234.00",
            period=("Oct 04, 2026", "Nov 03, 2026"),
            lauren=[],
            hernan=[],
            payment_dates="Oct 27 Oct 28",
        ),
    )
    g = client.post(f"/api/statements/{gap['statement_file_id']}/read").json()
    assert g["checks"][-1]["ok"] is False and g["tieout_ok"] is False


def test_read_errors(client: TestClient) -> None:
    assert client.post("/api/statements/999/read").status_code == 404
    assert client.get("/api/batches/999").status_code == 404
    assert client.post("/api/batches/999/approve").status_code == 404
    assert client.post("/api/batches/999/reject").status_code == 404
    other = _upload(client, "other.pdf", s.unknown())
    resp = client.post(f"/api/statements/{other['statement_file_id']}/read")
    assert resp.status_code == 422 and "isn't recognized" in resp.json()["detail"]
    assert other["can_read"] is False
    broken = _upload(client, "co-short.pdf", s.capitalone())  # detected, but no summary
    resp = client.post(f"/api/statements/{broken['statement_file_id']}/read")
    assert resp.status_code == 422 and "could not be read" in resp.json()["detail"]


def test_bofa_combined_statement_loads_both_accounts(client: TestClient, db: Session) -> None:
    st = _upload(client, "bofa.pdf", s.bofa_full())
    assert st["can_read"] is True
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    assert b["new_lines"] == 7

    lines = {ln["description"].split(" Conf")[0][:30]: ln for ln in b["lines"]}
    salary = lines["Transfer Kenility LLC Via WISE"]
    assert (salary["type"], salary["category_path"]) == ("income", "Salary / Hernan")
    to_sav = lines["Agent Assisted Automatic trans"]
    assert to_sav["type"] == "transfer"
    card = lines["CAPITAL ONE DES:MOBILE PMT ID:"]
    assert (card["type"], card["category_path"]) == ("transfer", "Transfers / Card Payment")
    assert lines["PAYPAL DES:PURCHASE ID:FABLETI"]["category_path"] == "Shopping / Clothing"
    zelle = lines["Zelle payment to TEST PERSON"]
    assert (zelle["type"], zelle["category_path"]) == ("expense", None)
    fee = lines["Monthly Maintenance Fee"]
    assert (fee["type"], fee["category_path"]) == ("fee_interest", "Financial Costs / Bank Fees")

    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 7
    rows = client.get("/api/transactions", params={"source": "statement"}).json()
    accounts = {r["description"][:20]: r["account_name"] for r in rows}
    assert accounts["Monthly Maintenance "] == "BofA Regular Savings"
    assert accounts["Zelle payment to TES"] == "BofA Adv Plus Banking"
    tx = db.scalars(select(Transaction).where(Transaction.type == "income")).one()
    assert (tx.pay_reference, tx.cash_month.isoformat()) == ("August", "2026-09-01")

    # Money in and out: the salary counts, transfers to savings and the card payment don't.
    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    assert Decimal(monthly["2026-09-01"]["income"]) == Decimal("4000")
    assert Decimal(monthly["2026-09-01"]["expenses"]) == Decimal("230")
    assert Decimal(monthly["2026-08-01"]["expenses"]) == Decimal("5")


def test_bofa_continuity_per_account(client: TestClient) -> None:
    first = _upload(
        client,
        "jul.pdf",
        s.bofa_full(
            period=("July 22, 2026", "August 22, 2026"), chk_begin="0.00", sav_begin="80.00"
        ),
    )
    client.post(f"/api/statements/{first['statement_file_id']}/read")
    # July ends at 2,245.00 / 100.00; August opens at 2,000.00 / 100.00.
    nxt = _upload(client, "aug.pdf", s.bofa_full())
    b = client.post(f"/api/statements/{nxt['statement_file_id']}/read").json()
    cont = {c["name"]: c for c in b["checks"] if c["name"].startswith("Opening balance")}
    assert (
        cont[
            "Opening balance BofA Adv Plus Banking = closing balance of the Aug 22, 2026 statement"
        ]["ok"]
        is False
    )
    assert (
        cont[
            "Opening balance BofA Regular Savings = closing balance of the Aug 22, 2026 statement"
        ]["ok"]
        is True
    )
    assert b["tieout_ok"] is False


def test_bofa_needs_both_accounts_linked(client: TestClient, db: Session) -> None:
    from sqlalchemy import update

    from app.models import Account

    db.execute(update(Account).where(Account.name == "BofA Regular Savings").values(last4=None))
    db.commit()
    st = _upload(client, "bofa.pdf", s.bofa_full())
    resp = client.post(f"/api/statements/{st['statement_file_id']}/read")
    assert resp.status_code == 422 and "•••• 1862" in resp.json()["detail"]


def test_pichincha_statement_loads_with_categories(client: TestClient) -> None:
    st = _upload(client, "pich.pdf", s.pichincha_full())
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    lines = {ln["description"]: ln for ln in b["lines"]}
    expect = {
        'SU PAGO "MUCHAS GRACIAS"': ("transfer", "Transfers / Card Payment"),
        "INT. FINANCIAMIENTO": ("fee_interest", "Financial Costs / Credit Card Interest"),
        "CONT_FIN_SOLCA_C.ROT**": ("expense", "Financial Costs / SOLCA Contribution"),
        "RET IVA SERV DIGITAL 100%": ("expense", "Financial Costs / Taxes on Digital Services"),
        "ND PRECANCELACION DIF. C.": ("savings", "Savings & Debt / Extra Debt Payoff"),
        "UBER *ONE MEMBERSHIP U V": ("expense", "Subscriptions & Software / Memberships"),
        "GOOGLE *YouTubeA M": ("expense", "Subscriptions & Software / Media"),
        "CONECEL VARIOS UIO": ("expense", "Utilities / Phone/Internet"),
    }
    for desc, (type_, path) in expect.items():
        assert (lines[desc]["type"], lines[desc]["category_path"]) == (type_, path), desc
    assert lines['SU PAGO "MUCHAS GRACIAS"']["person"] == "Hernan"  # the account owner
    assert lines["UBER *ONE MEMBERSHIP U V"]["cardholder"] == "6331"
    assert lines["TIENDA DE PRUEBA DIFERIDO"]["pay_reference"] == "2/6"
    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 10


def test_months_with_excel_history_do_not_count_statement_lines(
    client: TestClient, db: Session
) -> None:
    from datetime import date

    st = _upload(client, "co.pdf", s.capitalone_full())
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve")
    # A history row for September 2026 (as if the workbook covered it).
    db.add(
        Transaction(
            natural_key="excel-test-sep",
            txn_date=date(2026, 9, 1),
            cash_month=date(2026, 9, 1),
            amount=Decimal("-1000"),
            description_raw="Capital One",
            type="debt_payment",
            source="excel_history",
            status="confirmed",
        )
    )
    db.commit()
    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    sep = monthly["2026-09-01"]
    assert (Decimal(sep["expenses"]), Decimal(sep["debt_payments"])) == (
        Decimal("0"),
        Decimal("1000"),
    )
    assert Decimal(monthly["2026-10-01"]["expenses"]) == Decimal(
        "50"
    )  # no history: statements count
    cats = client.get("/api/cashflow/categories", params={"year": 2026}).json()
    assert not [c for c in cats if c["cash_month"] == "2026-09-01" and c["type"] == "expense"]
    # The lines are still loaded and listed.
    assert len(client.get("/api/transactions", params={"month": "2026-09-01"}).json()) == 10


def test_produbanco_statement_loads_with_iess_split(client: TestClient) -> None:
    st = _upload(client, "prod.pdf", s.produbanco_full())
    assert st["can_read"] is True and st["accounts"][0]["name"] == "Produbanco Ahorros Hernan"
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    by_amount = {ln["amount"]: ln for ln in b["lines"]}
    expect = {
        "-100.0000": ("expense", "Household Staff / Empleada IESS"),
        "-500.0000": ("expense", "Housing / Mortgage BIESS"),
        "-0.4100": ("fee_interest", "Financial Costs / Bank Fees"),
        "-1080.0000": ("transfer", "Transfers / Card Payment"),
        "0.0100": ("income", "Interest Earned"),
        "600.0000": ("income", None),  # who sent it is a question for F9
    }
    for amt, (type_, path) in expect.items():
        ln = by_amount[amt]
        assert (ln["type"], ln["category_path"]) == (type_, path), ln["description"]
        assert ln["person"] == "Hernan"
    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 10


def test_produbanco_lauren_and_continuity(client: TestClient) -> None:
    jul = _upload(client, "jul.pdf", s.produbanco_full(account="88888885555"))
    assert jul["accounts"][0]["name"] == "Produbanco Lauren"
    b = client.post(f"/api/statements/{jul['statement_file_id']}/read").json()
    assert b["tieout_ok"] and {ln["person"] for ln in b["lines"]} == {"Lauren"}
    client.post(f"/api/batches/{b['batch_id']}/approve")
    aug_lines = [("Ago 3", "1", "DEBITO VISA", "-10.00")]
    aug = _upload(
        client,
        "aug.pdf",
        s.produbanco_full(
            account="88888885555",
            opening="999.00",  # July closed at 243.40
            period="Del 01 Ago 2026 Al 31 Ago 2026",
            lines=aug_lines,
        ),
    )
    b2 = client.post(f"/api/statements/{aug['statement_file_id']}/read").json()
    failed = [c["name"] for c in b2["checks"] if not c["ok"]]
    assert failed == ["Opening balance = closing balance of the Jul 31, 2026 statement"]


def test_diners_statement_loads_with_cardholders(client: TestClient) -> None:
    st = _upload(client, "din.pdf", s.diners_full())
    assert st["accounts"][0]["name"] == "Diners Club Hernan" and st["can_read"] is True
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    lines = {ln["description"]: ln for ln in b["lines"]}
    expect = {
        'SU PAGO "MUCHAS GRACIAS"': ("transfer", "Transfers / Card Payment"),
        "INTERESES DE MORA": ("fee_interest", "Financial Costs / Credit Card Interest"),
        "GASTO GESTION COBRANZAS": ("fee_interest", "Financial Costs / Bank Fees"),
        "CONT_FIN_SOLCA_C.ROT**": ("expense", "Financial Costs / SOLCA Contribution"),
        "RET IVA SERV DIGITAL 100%": ("expense", "Financial Costs / Taxes on Digital Services"),
        "SUPERMAXI CUMBAYA": ("expense", "Groceries / Supermarket"),
    }
    for desc, (type_, path) in expect.items():
        assert (lines[desc]["type"], lines[desc]["category_path"]) == (type_, path), desc
    assert lines["SUPERMAXI CUMBAYA"]["person"] == "Lauren"  # the additional card
    assert lines['SU PAGO "MUCHAS GRACIAS"']["person"] == "Hernan"  # the account owner
    assert lines["COLEGIO DE PRUEBA CUMBAYA"]["pay_reference"] == "8/12"
    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 12


def test_continuity_skips_a_missing_month(client: TestClient) -> None:
    jul = _upload(client, "jul.pdf", s.produbanco_full())
    b = client.post(f"/api/statements/{jul['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve")
    # September, with August missing: nothing to compare the opening balance with.
    sep = _upload(
        client,
        "sep.pdf",
        s.produbanco_full(
            opening="50.00",
            period="Del 01 Sep 2026 Al 30 Sep 2026",
            lines=[("Sep 3", "1", "DEBITO VISA", "-10.00")],
        ),
    )
    b2 = client.post(f"/api/statements/{sep['statement_file_id']}/read").json()
    assert b2["tieout_ok"] is True
    assert not any("closing balance of the" in c["name"] for c in b2["checks"])


@pytest.mark.skipif(not ocr.available(), reason="tesseract is not installed")
def test_pacificard_screenshot_is_read_with_ocr_and_loads(client: TestClient) -> None:
    st = _upload(client, "pacificard.pdf", s.pacificard_full())
    assert (
        st["source"] == "pacificard" and st["accounts"][0]["name"] == "Pacificard Mastercard Black"
    )
    assert (st["period_start"], st["period_end"]) == ("2026-08-25", "2026-09-24")
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    lines = {ln["description"]: ln for ln in b["lines"]}
    assert lines["SUPERMAXI CUMBAYA QUITO"]["category_path"] == "Groceries / Supermarket"
    assert lines["SU PAGO PAGO DIRECTO BDP GUAYAQUI"]["category_path"] == "Transfers / Card Payment"
    assert lines["SERV. RENOVACION TARJ/CHIP"]["person"] == "Lauren"
    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 9


def test_ocr_failure_is_reported(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ingestion import stage

    st = _upload(client, "co.pdf", s.capitalone_full())

    def broken(*_a: object, **_k: object) -> list[str]:
        raise ocr.OcrError("OCR (tesseract) is not installed on this server.")

    monkeypatch.setitem(stage.OCR_SOURCES, "capitalone", ocr.first_page)
    monkeypatch.setattr(stage.ocr, "ocr_pages", broken)
    resp = client.post(f"/api/statements/{st['statement_file_id']}/read")
    assert resp.status_code == 422 and "not installed" in resp.json()["detail"]
