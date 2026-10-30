"""Electronic invoices (F21, ADR-021): what was bought, product by product.

Ecuador's electronic invoices (SRI "facturas") arrive as XML: by email from each vendor (the Gmail
script posts them to /api/inbox) or uploaded on the Purchases page. Each one is
- read (`parse`): the issuer, number, date, totals and every product line, checked so the lines
  add up to the invoice's subtotal;
- stored once (`store`), keyed by SRI's 49-digit access key, so the same invoice again is a
  duplicate;
- matched to the card or bank line that paid it (`link_pending`): the same total, one day before
  to four days after the invoice date, a purchase not already matched;
- grouped product by product (`group_lines`): a confirmed rule for that product first, then a few
  Spanish keywords; the rest wait for a person (or Claude's suggestion) on the Purchases page.

The buyer's identification (cédula or RUC) and address are never stored.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    PRODUCT_GROUPS,
    Invoice,
    InvoiceLine,
    LoadLog,
    ProductRule,
    Transaction,
)

ZERO = Decimal(0)
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.02")  # lines vs the invoice's subtotal, after rounding
MATCH_BEFORE = timedelta(days=1)
MATCH_AFTER = timedelta(days=4)  # cards post a day or few after the purchase
MAX_BYTES = 2 * 1024 * 1024
FACTURA = "01"  # SRI codDoc for an invoice; credit notes, retentions etc. are skipped


class InvoiceError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


class NotAnInvoice(InvoiceError):
    """A valid SRI document that isn't an invoice (a credit note, a retention): skipped."""


@dataclass
class Line:
    line_no: int
    code: str | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    subtotal: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return (self.subtotal + self.tax).quantize(CENT)


@dataclass
class Parsed:
    access_key: str
    issuer_ruc: str
    issuer_name: str
    number: str
    issue_date: date
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    lines: list[Line] = field(default_factory=list)


# ---------------------------------------------------------------- reading
def _dec(text: str | None) -> Decimal:
    try:
        return Decimal((text or "0").strip())
    except InvalidOperation:
        return ZERO


def _text(el: Element | None, path: str) -> str:
    found = el.find(path) if el is not None else None
    return (found.text or "").strip() if found is not None and found.text else ""


def _local(el: Element) -> None:
    """Drop XML namespaces so paths read the same with or without them."""
    for e in el.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _load(xml: bytes) -> Element:
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise InvoiceError("This isn't an electronic invoice (XML).") from exc
    _local(root)
    # An authorized document wraps the invoice: <autorizacion><comprobante><![CDATA[<factura>…
    if root.tag != "factura":
        inner = root.find(".//comprobante")
        if inner is not None and inner.text and inner.text.strip().startswith("<"):
            return _load(inner.text.strip().encode("utf-8"))
        found = root.find(".//factura")
        if found is not None:
            return found
        tags = {"notaCredito", "notaDebito", "comprobanteRetencion", "guiaRemision"}
        if root.tag in tags or any(root.find(f".//{t}") is not None for t in tags):
            raise NotAnInvoice("An SRI document that isn't an invoice (a credit note or similar).")
        raise InvoiceError("This XML isn't an SRI electronic invoice.")
    return root


def parse(xml: bytes) -> Parsed:
    if len(xml) > MAX_BYTES:
        raise InvoiceError("The file is larger than 2 MB.", 413)
    f = _load(xml)
    info_t, info_f = f.find("infoTributaria"), f.find("infoFactura")
    if info_t is None or info_f is None:
        raise InvoiceError("The invoice has no infoTributaria / infoFactura section.")
    cod = _text(info_t, "codDoc")
    if cod and cod != FACTURA:
        raise NotAnInvoice(f"An SRI document of type {cod}, not an invoice.")
    key = _text(info_t, "claveAcceso")
    if not re.fullmatch(r"\d{49}", key):
        raise InvoiceError("The invoice has no valid access key (claveAcceso).")
    try:
        issued = datetime.strptime(_text(info_f, "fechaEmision"), "%d/%m/%Y").date()
    except ValueError as exc:
        raise InvoiceError("The invoice's date (fechaEmision) can't be read.") from exc

    lines = []
    for i, d in enumerate(f.findall("detalles/detalle"), start=1):
        tax = sum((_dec(t.findtext("valor")) for t in d.findall("impuestos/impuesto")), ZERO)
        lines.append(
            Line(
                line_no=i,
                code=(_text(d, "codigoPrincipal") or _text(d, "codigoInterno") or None),
                description=_text(d, "descripcion")[:300] or "?",
                quantity=_dec(_text(d, "cantidad")),
                unit_price=_dec(_text(d, "precioUnitario")),
                discount=_dec(_text(d, "descuento")).quantize(CENT),
                subtotal=_dec(_text(d, "precioTotalSinImpuesto")).quantize(CENT),
                tax=tax.quantize(CENT),
            )
        )
    subtotal = _dec(_text(info_f, "totalSinImpuestos")).quantize(CENT)
    total = _dec(_text(info_f, "importeTotal")).quantize(CENT)
    tax = sum(
        (_dec(t.findtext("valor")) for t in info_f.findall("totalConImpuestos/totalImpuesto")),
        ZERO,
    ).quantize(CENT)
    if not lines:
        raise InvoiceError("The invoice has no product lines.")
    added = sum((ln.subtotal for ln in lines), ZERO)
    if abs(added - subtotal) > TOLERANCE:
        raise InvoiceError(
            f"The products add up to {added} but the invoice says {subtotal} before tax."
        )
    number = "-".join(
        p
        for p in (_text(info_t, "estab"), _text(info_t, "ptoEmi"), _text(info_t, "secuencial"))
        if p
    )
    return Parsed(
        access_key=key,
        issuer_ruc=_text(info_t, "ruc")[:13],
        issuer_name=(_text(info_t, "nombreComercial") or _text(info_t, "razonSocial"))[:300],
        number=number[:20],
        issue_date=issued,
        subtotal=subtotal,
        tax=tax,
        total=total,
        lines=lines,
    )


# ---------------------------------------------------------------- product groups
def product_key(description: str) -> str:
    """'Leche  Entera VITA 1L ' and 'LECHE ENTERA VITA 1L' are the same product."""
    folded = unicodedata.normalize("NFKD", description)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(folded.upper().split())[:300]


# A few words that are hard to get wrong; the rest is a person's (or Claude's) call.
KEYWORDS: tuple[tuple[str, str], ...] = (
    # Checked in order, so a sweet with milk is a sweet: "CHOCOLATE CON LECHE".
    ("GALLETA", "Snacks & Sweets"),
    ("CHOCOLATE", "Snacks & Sweets"),
    ("PAPAS FRITAS", "Snacks & Sweets"),
    ("PANAL", "Baby"),
    ("COMPOTA", "Baby"),
    ("LECHE", "Dairy & Eggs"),
    ("YOGURT", "Dairy & Eggs"),
    ("QUESO", "Dairy & Eggs"),
    ("HUEVO", "Dairy & Eggs"),
    ("MANTEQUILLA", "Dairy & Eggs"),
    ("POLLO", "Meat & Fish"),
    ("CARNE", "Meat & Fish"),
    ("RES", "Meat & Fish"),
    ("CERDO", "Meat & Fish"),
    ("JAMON", "Meat & Fish"),
    ("SALCHICHA", "Meat & Fish"),
    ("ATUN", "Meat & Fish"),
    ("SALMON", "Meat & Fish"),
    ("CAMARON", "Meat & Fish"),
    ("PESCADO", "Meat & Fish"),
    ("TOMATE", "Fruit & Vegetables"),
    ("CEBOLLA", "Fruit & Vegetables"),
    ("PAPA", "Fruit & Vegetables"),
    ("BANANO", "Fruit & Vegetables"),
    ("MANZANA", "Fruit & Vegetables"),
    ("AGUACATE", "Fruit & Vegetables"),
    ("LIMON", "Fruit & Vegetables"),
    ("FRUTILLA", "Fruit & Vegetables"),
    ("LECHUGA", "Fruit & Vegetables"),
    ("ZANAHORIA", "Fruit & Vegetables"),
    ("PAN", "Bakery"),
    ("ARROZ", "Pantry"),
    ("FIDEO", "Pantry"),
    ("ACEITE", "Pantry"),
    ("AZUCAR", "Pantry"),
    ("HARINA", "Pantry"),
    ("SAL", "Pantry"),
    ("CAFE", "Pantry"),
    ("AGUA", "Drinks"),
    ("JUGO", "Drinks"),
    ("GASEOSA", "Drinks"),
    ("CERVEZA", "Alcohol"),
    ("VINO", "Alcohol"),
    ("DETERGENTE", "Household & Cleaning"),
    ("CLORO", "Household & Cleaning"),
    ("SUAVIZANTE", "Household & Cleaning"),
    ("PAPEL HIGIENICO", "Household & Cleaning"),
    ("LAVAVAJILLA", "Household & Cleaning"),
    ("SHAMPOO", "Personal Care"),
    ("JABON", "Personal Care"),
    ("PASTA DENTAL", "Personal Care"),
    ("DESODORANTE", "Personal Care"),
    ("PERRO", "Pets"),
    ("GATO", "Pets"),
)


def keyword_group(key: str) -> str | None:
    """Whole words only ('PAN' is bread, 'PANELA' isn't; 'PANALES' is a plural of 'PANAL')."""
    words = key.split()
    text = f" {key} "
    for word, group in KEYWORDS:
        if " " in word:
            if f" {word} " in text:
                return group
        elif any(w == word or w in (word + "S", word + "ES") for w in words):
            return group
    return None


def group_lines(db: Session, lines: list[InvoiceLine]) -> None:
    """A group for each line without a person's choice: the product's rule, else a keyword."""
    keys = {ln.product_key for ln in lines}
    rules = {
        r.product_key: r.product_group
        for r in db.scalars(select(ProductRule).where(ProductRule.product_key.in_(keys)))
    }
    for ln in lines:
        if ln.group_source == "confirmed":
            continue
        if ln.product_key in rules:
            ln.product_group, ln.group_source = rules[ln.product_key], "rule"
        elif ln.group_source != "claude":
            group = keyword_group(ln.product_key)
            ln.product_group, ln.group_source = (group, "keyword") if group else (None, None)


def confirm(db: Session, key: str, group: str, user: str) -> int:
    """A person's group for a product: saved as a rule and applied to every line with it.
    Returns how many lines changed."""
    if group not in PRODUCT_GROUPS:
        raise InvoiceError(f"Unknown product group {group!r}.")
    rule = db.scalar(select(ProductRule).where(ProductRule.product_key == key))
    if rule is None:
        db.add(ProductRule(product_key=key, product_group=group, created_by=user[:320]))
    else:
        rule.product_group, rule.created_by = group, user[:320]
    lines = list(db.scalars(select(InvoiceLine).where(InvoiceLine.product_key == key)))
    for ln in lines:
        ln.product_group, ln.group_source = group, "confirmed"
    db.commit()
    return len(lines)


# ---------------------------------------------------------------- storing and matching
@dataclass
class Stored:
    invoice: Invoice
    duplicate: bool


def store(db: Session, p: Parsed, user: str) -> Stored:
    existing = db.scalar(select(Invoice).where(Invoice.access_key == p.access_key))
    if existing is not None:
        return Stored(existing, True)
    inv = Invoice(
        access_key=p.access_key,
        issuer_ruc=p.issuer_ruc,
        issuer_name=p.issuer_name,
        number=p.number,
        issue_date=p.issue_date,
        subtotal=p.subtotal,
        tax=p.tax,
        total=p.total,
        received_by=user[:320],
        lines=[
            InvoiceLine(
                line_no=ln.line_no,
                code=ln.code[:60] if ln.code else None,
                description=ln.description,
                product_key=product_key(ln.description),
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                discount=ln.discount,
                subtotal=ln.subtotal,
                tax=ln.tax,
                total=ln.total,
            )
            for ln in p.lines
        ],
    )
    db.add(inv)
    db.flush()
    group_lines(db, inv.lines)
    _link(db, inv)
    db.add(
        LoadLog(
            source="invoice",
            loaded_by=user[:320],
            rows_loaded=len(inv.lines),
            summary=f"Invoice {inv.number} from {inv.issuer_name[:80]}, {inv.issue_date}: "
            f"{inv.total}",
        )
    )
    db.commit()
    return Stored(inv, False)


def _link(db: Session, inv: Invoice) -> bool:
    """The one purchase that paid this invoice: the same amount, close in date, not taken."""
    taken = select(Invoice.transaction_id).where(Invoice.transaction_id.is_not(None))
    candidates = list(
        db.scalars(
            select(Transaction).where(
                Transaction.amount == -inv.total,
                Transaction.txn_date >= inv.issue_date - MATCH_BEFORE,
                Transaction.txn_date <= inv.issue_date + MATCH_AFTER,
                Transaction.transaction_id.not_in(taken),
            )
        )
    )
    if len(candidates) != 1:
        return False
    inv.transaction_id = candidates[0].transaction_id
    return True


def link_pending(db: Session, since: date | None = None) -> int:
    """Match invoices still without their payment (statements arrive later than invoices)."""
    q = select(Invoice).where(Invoice.transaction_id.is_(None))
    if since is not None:
        q = q.where(Invoice.issue_date >= since)
    linked = sum(1 for inv in db.scalars(q) if _link(db, inv))
    if linked:
        db.commit()
    return linked


# ---------------------------------------------------------------- reading back
@dataclass
class GroupTotal:
    group: str  # "Not grouped yet" when no group
    amount: Decimal
    lines: int


def month_groups(db: Session, month: date) -> list[GroupTotal]:
    end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    rows = db.execute(
        select(
            InvoiceLine.product_group,
            func.sum(InvoiceLine.total),
            func.count(InvoiceLine.line_id),
        )
        .join(Invoice)
        .where(Invoice.issue_date >= month, Invoice.issue_date < end)
        .group_by(InvoiceLine.product_group)
    ).all()
    out = [
        GroupTotal(g or "Not grouped yet", Decimal(a or 0).quantize(CENT), n) for g, a, n in rows
    ]
    return sorted(out, key=lambda g: (-g.amount, g.group))


def month_invoices(db: Session, month: date) -> list[Invoice]:
    end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return list(
        db.scalars(
            select(Invoice)
            .where(Invoice.issue_date >= month, Invoice.issue_date < end)
            .order_by(Invoice.issue_date.desc(), Invoice.invoice_id.desc())
        )
    )
