"""Invoices from the SRI's list of received documents (ADR-037). A person downloads the month's
"Comprobantes electrónicos recibidos" report from SRI en línea and uploads it (or pastes it); the
app finds each 49-digit access key and asks the SRI's public authorization web service for that
invoice's authorized XML, which is then read like any other invoice (ADR-021).

No SRI password or session is used or stored: the authorization service answers by access key
alone. Only the access keys are sent to the SRI."""

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Invoice

KEY = re.compile(r"(?<!\d)\d{49}(?!\d)")
FACTURA = "01"
RETENCION = "07"
# Invoices, credit and debit notes and retenciones (ADR-062, ADR-064).
READ = (FACTURA, "04", "05", RETENCION)
TIMEOUT = 20  # seconds per access key
MAX_BYTES = 2_000_000
ENVELOPE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Header/><soapenv:Body>'
    "<ec:autorizacionComprobante><claveAccesoComprobante>{key}</claveAccesoComprobante>"
    "</ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>"
)


class SriError(Exception):
    """The SRI couldn't be reached or answered with something unreadable."""


@dataclass
class Keys:
    new: list[str] = field(default_factory=list)  # invoices not in the app yet
    stored: int = 0  # invoices already in the app
    other: int = 0  # other documents (guías de remisión, liquidaciones): not read


def doc_type(key: str) -> str:
    """The document type inside an access key: digits 9-10 ('01' factura, '04' nota de crédito,
    '07' retención)."""
    return key[8:10]


def find_keys(db: Session, text: str) -> Keys:
    """Every distinct access key in the text, sorted into new invoices, invoices already in the
    app and other documents."""
    seen: list[str] = []
    for k in KEY.findall(text):
        if k not in seen:
            seen.append(k)
    out = Keys()
    invoices = [k for k in seen if doc_type(k) in READ]
    out.other = len(seen) - len(invoices)
    have: set[str] = set()
    for i in range(0, len(invoices), 1000):
        chunk = invoices[i : i + 1000]
        have |= set(db.scalars(select(Invoice.access_key).where(Invoice.access_key.in_(chunk))))
    from app.services import iva

    have |= iva.known_keys(db, invoices)
    out.stored = len(have)
    out.new = [k for k in invoices if k not in have]
    return out


def _local(el: Element) -> None:
    for e in el.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


@dataclass
class Answer:
    state: str  # AUTORIZADO, NO AUTORIZADO, EN PROCESAMIENTO, or NONE (the SRI has no such key)
    xml: bytes | None  # the whole authorization answer, which the invoice reader understands
    reason: str = ""  # the SRI's own words when it refuses ("ERROR EN LA ESTRUCTURA…")


def read_answer(body: bytes) -> Answer:
    """The SOAP answer: how many documents the SRI found for the key, their state and the
    authorized document."""
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise SriError("The SRI's answer couldn't be read.") from exc
    _local(root)
    auth = root.find(".//autorizacion")
    if auth is None:
        return Answer("NONE", None)
    state = (auth.findtext("estado") or "").strip().upper()
    has_doc = (auth.findtext("comprobante") or "").strip().startswith("<")
    reasons = [
        " ".join(
            t
            for t in (m.findtext("mensaje"), m.findtext("informacionAdicional"))
            if t and t.strip()
        )
        for m in auth.findall("mensajes/mensaje")
    ]
    reason = "; ".join(r for r in reasons if r)[:300]
    return Answer(state, body if state == "AUTORIZADO" and has_doc else None, reason)


def ask(key: str) -> bytes:
    """POST one access key to the SRI's authorization service; the raw SOAP answer."""
    req = urllib.request.Request(
        get_settings().sri_authorization_url,
        data=ENVELOPE.format(key=key).encode(),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data: bytes = resp.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SriError(f"The SRI didn't answer ({exc}). Try again in a few minutes.") from exc
    if len(data) > MAX_BYTES:
        raise SriError("The SRI's answer was larger than 2 MB.")
    return data


def fetch(key: str) -> Answer:
    return read_answer(ask(key))
