"""ADR-062: the monthly IVA return from the SRI's documents. Synthetic data only: the numbers
mirror a real month's arithmetic (sales 3,308.70, purchases with credit 196.48, IVA withheld
421.31 and 1,462.79 carried in), not its documents."""

from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.fixtures.invoices import KEY, factura
from tests.unit.test_gastos import HERNAN_ID, buyers  # noqa: F401
from tests.unit.test_invoices import upload

OWN_RUC = HERNAN_ID + "001"


def key(n: int, cod: str = "01") -> str:
    k = KEY[:-3] + f"{n:03d}"
    return k[:8] + cod + k[10:]


def retencion(n: int, invoice: str, income: str, vat: str, *, v2: bool = False) -> bytes:
    taxes = (
        f"<codigo>1</codigo><codigoRetencion>303</codigoRetencion><baseImponible>1</baseImponible>"
        f"<porcentajeRetener>10</porcentajeRetener><valorRetenido>{income}</valorRetenido>",
        f"<codigo>2</codigo><codigoRetencion>3</codigoRetencion><baseImponible>1</baseImponible>"
        f"<porcentajeRetener>100</porcentajeRetener><valorRetenido>{vat}</valorRetenido>",
    )
    if v2:
        body = (
            f"<docsSustento><docSustento><codDocSustento>01</codDocSustento>"
            f"<numDocSustento>{invoice}</numDocSustento><retenciones>"
            + "".join(f"<retencion>{t}</retencion>" for t in taxes)
            + "</retenciones></docSustento></docsSustento>"
        )
    else:
        body = (
            "<impuestos>"
            + "".join(
                f"<impuesto>{t}<codDocSustento>01</codDocSustento>"
                f"<numDocSustento>{invoice}</numDocSustento></impuesto>"
                for t in taxes
            )
            + "</impuestos>"
        )
    doc = (
        f'<comprobanteRetencion id="comprobante" version="{"2.0.0" if v2 else "1.0.0"}">'
        f"<infoTributaria><razonSocial>CLIENTE DE PRUEBA S.A.</razonSocial>"
        f"<ruc>1799999999001</ruc><claveAcceso>{key(n, '07')}</claveAcceso><codDoc>07</codDoc>"
        f"<estab>001</estab><ptoEmi>001</ptoEmi><secuencial>{n:09d}</secuencial></infoTributaria>"
        f"<infoCompRetencion><fechaEmision>30/09/2026</fechaEmision>"
        f"<identificacionSujetoRetenido>{OWN_RUC}</identificacionSujetoRetenido>"
        f"<periodoFiscal>09/2026</periodoFiscal></infoCompRetencion>{body}</comprobanteRetencion>"
    )
    return (
        f"<autorizacion><estado>AUTORIZADO</estado><comprobante><![CDATA[{doc}]]>"
        "</comprobante></autorizacion>"
    ).encode()


def test_a_month_like_the_accountants(client: TestClient, buyers: None) -> None:  # noqa: F811
    sales = [
        factura(key=key(1), ruc=OWN_RUC, day="18/09/2026", lines=[("SERVICIOS", "1", "500", "15")]),
        factura(
            key=key(2), ruc=OWN_RUC, day="29/09/2026", lines=[("CONSULTORIA", "1", "2808.70", "15")]
        ),
    ]
    out = upload(client, *[(f"s{i}.xml", x) for i, x in enumerate(sales)])
    assert [o["outcome"] for o in out] == ["stored", "stored"]
    assert "for the IVA return" in out[0]["message"]
    # Business purchases (internet, phone, the accountant) and a personal one.
    buys = [
        (10, "1791111111001", [("INTERNET", "1", "34.99", "15")]),
        (11, "1792222222001", [("TELEFONO", "1", "20.99", "15")]),
        (12, "1793333333001", [("CONTABILIDAD", "1", "140.50", "15")]),
        (13, "1794444444001", [("CONSULTA MEDICA", "1", "60", "0")]),
    ]
    upload(
        client,
        *[
            (f"b{n}.xml", factura(key=key(n), ruc=ruc, buyer=HERNAN_ID, day="05/09/2026", lines=ls))
            for n, ruc, ls in buys
        ],
    )
    held = upload(client, ("r.xml", retencion(20, "001072140000123456", "280.87", "421.31")))
    assert held[0]["outcome"] == "stored" and "IVA 421.31" in held[0]["message"]
    assert upload(client, ("r.xml", retencion(20, "x", "1", "1")))[0]["outcome"] == "duplicate"

    for ruc in ("1791111111001", "1792222222001", "1793333333001"):
        r = client.put("/api/taxes/iva/issuers", json={"issuer_ruc": ruc, "iva_use": "business"})
        assert r.status_code == 204
    client.put(
        "/api/taxes/iva/issuers", json={"issuer_ruc": "1794444444001", "iva_use": "personal"}
    )
    assert (
        client.put(
            "/api/taxes/iva/issuers", json={"issuer_ruc": "1794444444001", "iva_use": "x"}
        ).status_code
        == 422
    )

    body = client.get("/api/taxes/iva", params={"month": "2026-09"}).json()
    assert body["person"] == "Hernan" and body["notes"]  # no opening credit yet
    opening = {"person": "Hernan", "month": "2026-09", "retention_credit": "1462.79"}
    assert client.put("/api/taxes/iva/opening", json=opening).status_code == 204

    body = client.get("/api/taxes/iva", params={"month": "2026-09"}).json()
    f = {k: Decimal(str(v)) for k, v in body["form"].items()}
    assert (f["f401"], f["f421"], f["f111"]) == (Decimal("3308.70"), Decimal("496.31"), 2)
    assert (f["f500"], f["f520"], f["f115"]) == (Decimal("196.48"), Decimal("29.47"), 3)
    assert f["f601"] == Decimal("466.84") and f["f606"] == Decimal("1462.79")
    assert f["f609"] == Decimal("421.31") and f["f617"] == Decimal("1417.26")
    assert f["f620"] == 0 and body["unclassified"] == 0 and not body["notes"]
    sale = next(s for s in body["sales"] if s["number"] == "072-140-000123456")
    assert Decimal(sale["iva_withheld"]) == Decimal("421.31")

    # October carries September's credit; a month with sales and no credit left would pay.
    oct_ = client.get("/api/taxes/iva", params={"month": "2026-10"}).json()["form"]
    assert Decimal(oct_["f606"]) == Decimal("1417.26") and Decimal(oct_["f620"]) == 0

    x = client.get("/api/taxes/iva/excel", params={"month": "2026-09"})
    assert x.status_code == 200 and "IVA_2026-09.xlsx" in x.headers["content-disposition"]
    wb = load_workbook(BytesIO(x.content))
    cells = [c for row in wb["2026-09"].iter_rows(values_only=True) for c in row if c]
    assert "VENTAS 15%" in cells and "COMPRAS 15%" in cells and "GASTOS PERSONALES" in cells
    form = {r[0]: r[2] for r in wb["Formulario 104"].iter_rows(min_row=2, values_only=True)}
    assert Decimal(str(form["617"])) == Decimal("1417.26")

    # Sales and retenciones are kept out of purchases.
    p = client.get("/api/invoices/purchases", params={"month": "2026-09"})
    assert p.status_code in (200, 404)
    assert client.get("/api/taxes/iva", params={"month": "bad"}).status_code == 422


def test_retencion_version_2_and_someone_elses(client: TestClient, buyers: None) -> None:  # noqa: F811
    out = upload(client, ("r.xml", retencion(30, "001002000000053", "10.00", "15.00", v2=True)))
    assert out[0]["outcome"] == "stored"
    body = client.get("/api/taxes/iva", params={"month": "2026-09", "person": "Hernan"}).json()
    w = body["withholdings"][0]
    assert (w["invoice_number"], Decimal(w["iva"])) == ("001002000000053", Decimal("15.00"))
    other = retencion(31, "1", "1", "1").replace(OWN_RUC.encode(), b"1799999999001")
    assert upload(client, ("o.xml", other))[0]["outcome"] == "skipped"


def test_sri_list_fetches_retenciones(client: TestClient) -> None:
    text = f"{key(40)} {key(41, '07')} {key(42, '04')}"
    k = client.post("/api/invoices/sri/keys", json={"text": text}).json()
    assert k["new"] == [key(40), key(41, "07")] and k["other"] == 1
