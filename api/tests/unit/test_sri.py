"""ADR-037: invoices fetched from the SRI by access key. The SRI is never called: its answers are
synthetic."""

import io
import urllib.error
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import sri
from tests.fixtures.invoices import KEY, factura
from tests.unit.test_invoices import USER, upload

OTHER = KEY[:-3] + "777"
CREDIT_NOTE = KEY[:8] + "04" + KEY[10:]


def soap(doc: bytes | None, state: str = "AUTORIZADO") -> bytes:
    """The SRI's answer for one access key: none, or one authorization with the document."""
    if doc is None:
        auths = ""
        n = 0
    else:
        auths = (
            f"<autorizaciones><autorizacion><estado>{state}</estado>"
            f"<numeroAutorizacion>{KEY}</numeroAutorizacion>"
            "<fechaAutorizacion>2026-10-28T18:46:43-05:00</fechaAutorizacion>"
            f"<ambiente>PRODUCCIÓN</ambiente><comprobante><![CDATA[{doc.decode()}]]>"
            "</comprobante><mensajes/></autorizacion></autorizaciones>"
        )
        n = 1
    return (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        '<ns2:autorizacionComprobanteResponse xmlns:ns2="http://ec.gob.sri.ws.autorizacion">'
        f"<RespuestaAutorizacionComprobante><claveAccesoConsultada>{KEY}"
        f"</claveAccesoConsultada><numeroComprobantes>{n}</numeroComprobantes>{auths}"
        "</RespuestaAutorizacionComprobante></ns2:autorizacionComprobanteResponse>"
        "</soap:Body></soap:Envelope>"
    ).encode()


def test_doc_type_and_answers() -> None:
    assert sri.doc_type(KEY) == "01" and sri.doc_type(CREDIT_NOTE) == "04"
    ok = sri.read_answer(soap(factura(wrapped=False)))
    assert ok.state == "AUTORIZADO" and ok.xml is not None
    assert sri.read_answer(soap(None)).state == "NONE"
    refused = sri.read_answer(soap(factura(wrapped=False), "NO AUTORIZADO"))
    assert refused.state == "NO AUTORIZADO" and refused.xml is None
    # A malformed key, as the SRI answered it in a real test (Nov 2026).
    bad = sri.read_answer(
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        b'<ns2:autorizacionComprobanteResponse xmlns:ns2="http://ec.gob.sri.ws.autorizacion">'
        b"<RespuestaAutorizacionComprobante><claveAccesoConsultada>123</claveAccesoConsultada>"
        b"<autorizaciones><autorizacion><estado>RECHAZADA</estado><mensajes><mensaje>"
        b"<identificador>80</identificador><mensaje>ERROR EN LA ESTRUCTURA DE LA CLAVE DE ACCESO"
        b"</mensaje><informacionAdicional>Error longitud clave acceso no valida."
        b"</informacionAdicional></mensaje></mensajes></autorizacion></autorizaciones>"
        b"</RespuestaAutorizacionComprobante></ns2:autorizacionComprobanteResponse>"
        b"</soap:Body></soap:Envelope>"
    )
    assert bad.state == "RECHAZADA" and bad.xml is None
    assert bad.reason == (
        "ERROR EN LA ESTRUCTURA DE LA CLAVE DE ACCESO Error longitud clave acceso no valida."
    )
    with pytest.raises(sri.SriError):
        sri.read_answer(b"<html>down for maintenance")


def test_keys_in_a_report(client: TestClient, db: Session) -> None:
    upload(client, ("a.xml", factura()))
    report = (
        "COMPROBANTE\tSERIE_COMPROBANTE\tRUC_EMISOR\tCLAVE_ACCESO\tNUMERO_AUTORIZACION\n"
        f"Factura\t072-140-000123456\t1799999999001\t{KEY}\t{KEY}\n"
        f"Factura\t072-140-000123457\t1799999999001\t{OTHER}\t{OTHER}\n"
        f"Notas de Crédito\t001-001-000000001\t1799999999001\t{CREDIT_NOTE}\t{CREDIT_NOTE}\n"
        "phone 0991234567 and a 50-digit run " + "1" * 50 + "\n"
    )
    out = client.post("/api/invoices/sri/keys", json={"text": report})
    assert out.status_code == 200, out.text
    assert out.json() == {"new": [OTHER], "stored": 1, "other": 1}


def test_fetching_stores_reports_and_survives_the_sri(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: dict[str, Any] = {
        KEY: soap(factura(wrapped=False)),
        OTHER: soap(None),
        CREDIT_NOTE: soap(factura(wrapped=False), "EN PROCESAMIENTO"),
    }
    rejected = KEY[:-3] + "444"
    answers[rejected] = soap(factura(wrapped=False), "RECHAZADA").replace(
        b"<mensajes/>",
        b"<mensajes><mensaje><mensaje>CLAVE NO REGISTRADA</mensaje></mensaje></mensajes>",
    )

    def fake_ask(key: str) -> bytes:
        a = answers.get(key)
        if a is None:
            raise sri.SriError("The SRI didn't answer (timed out). Try again in a few minutes.")
        return a  # type: ignore[no-any-return]

    monkeypatch.setattr(sri, "ask", fake_ask)
    late = KEY[:-3] + "555"
    resp = client.post(
        "/api/invoices/sri/fetch",
        json={"keys": [KEY, OTHER, CREDIT_NOTE, late, "123", rejected]},
        headers=USER,
    )
    assert resp.status_code == 200, resp.text
    got = [(r["outcome"], r["message"]) for r in resp.json()]
    assert got[0][0] == "stored" and "SUPER PRUEBA" in got[0][1]
    assert got[1] == ("rejected", "The SRI has no document with this access key.")
    assert got[2] == ("rejected", "The SRI is still processing it; try again later.")
    assert got[3][0] == "rejected" and "didn't answer" in got[3][1]
    assert got[4] == ("rejected", "Not an access key.")
    assert got[5] == ("rejected", "The SRI answered RECHAZADA. CLAVE NO REGISTRADA")
    again = client.post("/api/invoices/sri/fetch", json={"keys": [KEY]}).json()
    assert again[0]["outcome"] == "duplicate"
    too_many = client.post("/api/invoices/sri/fetch", json={"keys": [KEY] * 11})
    assert too_many.status_code == 422


class _Resp(io.BytesIO):
    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_ask_posts_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> _Resp:
        seen["url"], seen["body"], seen["timeout"] = req.full_url, req.data, timeout
        return _Resp(b"<ok/>")

    monkeypatch.setattr(sri.urllib.request, "urlopen", fake_urlopen)
    assert sri.ask(KEY) == b"<ok/>"
    assert seen["url"].startswith("https://cel.sri.gob.ec/")
    assert f"<claveAccesoComprobante>{KEY}</claveAccesoComprobante>".encode() in seen["body"]
    assert seen["timeout"] == sri.TIMEOUT

    def down(req: Any, timeout: int) -> _Resp:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(sri.urllib.request, "urlopen", down)
    with pytest.raises(sri.SriError, match="didn't answer"):
        sri.ask(KEY)

    monkeypatch.setattr(
        sri.urllib.request, "urlopen", lambda req, timeout: _Resp(b"x" * (sri.MAX_BYTES + 5))
    )
    with pytest.raises(sri.SriError, match="larger"):
        sri.ask(KEY)
