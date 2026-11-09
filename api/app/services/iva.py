"""The monthly IVA return (ADR-062), as the accountant prepares it: from the SRI's electronic
documents, what was sold (issued invoices), what was bought with IVA credit (received invoices of
issuers marked business), personal expenses, and the retenciones clients made, and from them the
Form 104 figures.

The return chains month to month: credit left over (field 615 for purchases, 617 for retenciones)
carries into the next month (605, 606). The first month's carried credit is entered once.
Not tax advice: the figures follow the form's arithmetic for a person who invoices services at
15% and has no imports, exports, fixed-asset sales or proportional credit.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    Invoice,
    SaleInvoice,
    TaxIssuerRule,
    Withholding,
)
from app.services import invoices
from app.services.recurring import add_months, first

ZERO = Decimal(0)
CENT = Decimal("0.01")
OPENING = "iva-opening:"  # core.app_setting: "<YYYY-MM>|<purchase credit>|<retention credit>"
RENTA, IVA = "1", "2"  # impuesto codigo in a comprobante de retención
# The general IVA rate since April 2024. The form's IVA is the rate on the month's taxed base
# (an invoice's own tax total can include ICE and other charges).
RATE = Decimal("0.15")


class IvaError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- reading documents
def _root(xml: bytes) -> Element:
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise invoices.InvoiceError("This isn't an SRI electronic document (XML).") from exc
    invoices._local(root)
    inner = root.find(".//comprobante")
    if root.tag not in ("factura", "comprobanteRetencion") and inner is not None and inner.text:
        return _root(inner.text.strip().encode("utf-8"))
    return root


def _dec(v: str | None) -> Decimal:
    return invoices._dec(v).quantize(CENT)


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _number(info_t: Element | None) -> str:
    return "-".join(
        p for p in (invoices._text(info_t, k) for k in ("estab", "ptoEmi", "secuencial")) if p
    )[:20]


@dataclass
class ParsedSale:
    access_key: str
    person: str
    number: str
    issue_date: date
    buyer_name: str
    base_taxed: Decimal
    base_zero: Decimal
    tax: Decimal
    total: Decimal


def own_sale(xml: bytes) -> ParsedSale | None:
    """An invoice issued by someone in the household (their RUC is their cédula + 001), or None."""
    f = _root(xml)
    if f.tag != "factura":
        return None
    info_t, info_f = f.find("infoTributaria"), f.find("infoFactura")
    person = invoices.buyer_person(invoices._text(info_t, "ruc"))
    if person is None or info_f is None:
        return None
    taxed = zero = tax = ZERO
    for t in info_f.findall("totalConImpuestos/totalImpuesto"):
        base, value = _dec(t.findtext("baseImponible")), _dec(t.findtext("valor"))
        if (t.findtext("codigo") or "").strip() == "2" and value > 0:
            taxed, tax = taxed + base, tax + value
        else:
            zero += base
    try:
        issued = datetime.strptime(invoices._text(info_f, "fechaEmision"), "%d/%m/%Y").date()
    except ValueError as exc:
        raise invoices.InvoiceError("The invoice's date (fechaEmision) can't be read.") from exc
    return ParsedSale(
        access_key=invoices._text(info_t, "claveAcceso"),
        person=person,
        number=_number(info_t),
        issue_date=issued,
        buyer_name=invoices._text(info_f, "razonSocialComprador")[:300] or "?",
        base_taxed=taxed,
        base_zero=zero,
        tax=tax,
        total=_dec(invoices._text(info_f, "importeTotal")),
    )


@dataclass
class ParsedWithholding:
    access_key: str
    person: str
    issuer_ruc: str
    issuer_name: str
    number: str
    issue_date: date
    period: date
    invoice_number: str | None
    income_tax: Decimal
    iva: Decimal


def withholding(xml: bytes) -> ParsedWithholding | None:
    """A comprobante de retención (version 1 or 2) made to someone in the household, or None."""
    r = _root(xml)
    if r.tag != "comprobanteRetencion":
        found = r.find(".//comprobanteRetencion")
        if found is None:
            return None
        r = found
    info_t, info = r.find("infoTributaria"), r.find("infoCompRetencion")
    person = invoices.buyer_person(invoices._text(info, "identificacionSujetoRetenido"))
    if person is None:
        return None
    try:
        issued = datetime.strptime(invoices._text(info, "fechaEmision"), "%d/%m/%Y").date()
        period = datetime.strptime(invoices._text(info, "periodoFiscal"), "%m/%Y").date()
    except ValueError as exc:
        raise invoices.InvoiceError("The retención's dates can't be read.") from exc
    income = vat = ZERO
    support: str | None = None
    taxes = r.findall("impuestos/impuesto")  # version 1
    if taxes:
        support = _digits(taxes[0].findtext("numDocSustento")) or None
    else:  # version 2: docsSustento/docSustento/retenciones/retencion
        for doc in r.findall("docsSustento/docSustento"):
            support = support or _digits(doc.findtext("numDocSustento")) or None
            taxes += doc.findall("retenciones/retencion")
    for t in taxes:
        value = _dec(t.findtext("valorRetenido"))
        code = (t.findtext("codigo") or "").strip()
        if code == RENTA:
            income += value
        elif code == IVA:
            vat += value
    return ParsedWithholding(
        access_key=invoices._text(info_t, "claveAcceso"),
        person=person,
        issuer_ruc=invoices._text(info_t, "ruc")[:13],
        issuer_name=(
            invoices._text(info_t, "razonSocial") or invoices._text(info_t, "nombreComercial")
        )[:300],
        number=_number(info_t),
        issue_date=issued,
        period=period,
        invoice_number=support[:20] if support else None,
        income_tax=income,
        iva=vat,
    )


def store_sale(db: Session, p: ParsedSale, user: str) -> tuple[SaleInvoice, bool]:
    found = db.scalar(select(SaleInvoice).where(SaleInvoice.access_key == p.access_key))
    if found is not None:
        return found, True
    s = SaleInvoice(**p.__dict__, received_by=user[:320])
    db.add(s)
    db.commit()
    return s, False


def store_withholding(db: Session, p: ParsedWithholding, user: str) -> tuple[Withholding, bool]:
    found = db.scalar(select(Withholding).where(Withholding.access_key == p.access_key))
    if found is not None:
        return found, True
    w = Withholding(**p.__dict__, received_by=user[:320])
    db.add(w)
    db.commit()
    return w, False


def known_keys(db: Session, keys: list[str]) -> set[str]:
    have: set[str] = set()
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        for model in (SaleInvoice, Withholding):
            have |= set(db.scalars(select(model.access_key).where(model.access_key.in_(chunk))))
    return have


# ---------------------------------------------------------------- the month
@dataclass
class SaleRow:
    number: str
    issue_date: date
    buyer_name: str
    base_taxed: Decimal
    base_zero: Decimal
    tax: Decimal
    total: Decimal
    income_tax_withheld: Decimal
    iva_withheld: Decimal


@dataclass
class PurchaseRow:
    invoice_id: int
    issuer_ruc: str
    issuer_name: str
    number: str
    issue_date: date
    base_taxed: Decimal
    base_zero: Decimal
    tax: Decimal
    total: Decimal
    iva_use: str | None  # business, personal, none, or None when nobody said
    access_key: str


@dataclass
class WithholdingRow:
    issuer_name: str
    number: str
    issue_date: date
    invoice_number: str | None
    income_tax: Decimal
    iva: Decimal


@dataclass
class Form:
    """The Form 104 fields that aren't zero for this kind of return."""

    f401: Decimal = ZERO  # sales taxed above 0%, gross = net (411)
    f421: Decimal = ZERO  # IVA on them (= 429, 482, 484, 499)
    f403: Decimal = ZERO  # sales at 0%
    f500: Decimal = ZERO  # purchases with credit, taxed above 0% (= 510)
    f520: Decimal = ZERO  # IVA on them (= 529, 564)
    f507: Decimal = ZERO  # purchases at 0%
    f111: int = 0  # sales documents issued
    f115: int = 0  # purchase documents received
    f601: Decimal = ZERO  # IVA caused (499 - 564 when positive)
    f602: Decimal = ZERO  # credit of the month (564 - 499 when positive)
    f605: Decimal = ZERO  # purchase credit from last month (615 before)
    f606: Decimal = ZERO  # retention credit from last month (617 before)
    f609: Decimal = ZERO  # IVA withheld by clients this month
    f615: Decimal = ZERO  # purchase credit to next month
    f617: Decimal = ZERO  # retention credit to next month
    f620: Decimal = ZERO  # to pay (= 699, 902, 999 without interest or fines)


@dataclass
class IvaMonth:
    person: str
    month: date
    sales: list[SaleRow]
    purchases: list[PurchaseRow]  # every invoice received by the person this month
    withholdings: list[WithholdingRow]
    form: Form
    opening_month: date | None
    unclassified: int = 0
    income_tax_withheld: Decimal = ZERO
    notes: list[str] = field(default_factory=list)


def opening(db: Session, person: str) -> tuple[date, Decimal, Decimal] | None:
    s = db.get(AppSetting, OPENING + person)
    if s is None:
        return None
    m, purchase, retention = s.setting_value.split("|")
    return date.fromisoformat(f"{m}-01"), Decimal(purchase), Decimal(retention)


def set_opening(
    db: Session, person: str, month: date, purchase: Decimal, retention: Decimal, user: str
) -> None:
    """The credit carried into `month` from before the app (fields 605 and 606)."""
    if purchase < 0 or retention < 0:
        raise IvaError("Credits are positive amounts.")
    value = f"{first(month):%Y-%m}|{purchase:.2f}|{retention:.2f}"
    s = db.get(AppSetting, OPENING + person)
    if s is None:
        db.add(AppSetting(setting_key=OPENING + person, setting_value=value, updated_by=user[:200]))
    else:
        s.setting_value, s.updated_by = value, user[:200]
    db.commit()


def set_issuer(db: Session, issuer_ruc: str, iva_use: str, user: str) -> None:
    if iva_use not in ("business", "personal", "none"):
        raise IvaError("Choose business, personal or none.")
    r = db.scalar(select(TaxIssuerRule).where(TaxIssuerRule.issuer_ruc == issuer_ruc))
    if r is None:
        db.add(TaxIssuerRule(issuer_ruc=issuer_ruc, iva_use=iva_use, created_by=user[:320]))
    else:
        r.iva_use, r.created_by = iva_use, user[:320]
    db.commit()


def _bases(inv: Invoice) -> tuple[Decimal, Decimal]:
    taxed = sum((ln.subtotal for ln in inv.lines if ln.tax > 0), ZERO)
    return taxed.quantize(CENT), (inv.subtotal - taxed).quantize(CENT)


def _one(db: Session, person: str, month: date, carried: tuple[Decimal, Decimal]) -> IvaMonth:
    m, nxt = first(month), add_months(first(month), 1)
    rules = {r.issuer_ruc: r.iva_use for r in db.scalars(select(TaxIssuerRule))}
    held = list(
        db.scalars(
            select(Withholding)
            .where(Withholding.person == person, Withholding.period == m)
            .order_by(Withholding.issue_date)
        )
    )
    by_invoice: dict[str, list[Withholding]] = {}
    for w in held:
        if w.invoice_number:
            by_invoice.setdefault(_digits(w.invoice_number)[-9:], []).append(w)
    sales = []
    for s in db.scalars(
        select(SaleInvoice)
        .where(SaleInvoice.person == person, SaleInvoice.issue_date >= m)
        .where(SaleInvoice.issue_date < nxt)
        .order_by(SaleInvoice.issue_date, SaleInvoice.number)
    ):
        ws = by_invoice.get(_digits(s.number)[-9:], [])
        sales.append(
            SaleRow(
                s.number,
                s.issue_date,
                s.buyer_name,
                s.base_taxed,
                s.base_zero,
                s.tax,
                s.total,
                sum((w.income_tax for w in ws), ZERO),
                sum((w.iva for w in ws), ZERO),
            )
        )
    purchases = []
    for inv in db.scalars(
        select(Invoice)
        .where(Invoice.person == person, Invoice.issue_date >= m, Invoice.issue_date < nxt)
        .order_by(Invoice.issue_date, Invoice.invoice_id)
    ):
        taxed, zero = _bases(inv)
        use = rules.get(inv.issuer_ruc) or ("personal" if inv.gp_category else None)
        purchases.append(
            PurchaseRow(
                inv.invoice_id,
                inv.issuer_ruc,
                inv.issuer_name,
                inv.number,
                inv.issue_date,
                taxed,
                zero,
                inv.tax,
                inv.total,
                use,
                inv.access_key,
            )
        )

    f = Form()
    f.f401 = sum((s.base_taxed for s in sales), ZERO)
    f.f421 = (f.f401 * RATE).quantize(CENT, ROUND_HALF_UP)
    f.f403 = sum((s.base_zero for s in sales), ZERO)
    f.f111 = len(sales)
    business = [p for p in purchases if p.iva_use == "business"]
    f.f500 = sum((p.base_taxed for p in business), ZERO)
    f.f520 = (f.f500 * RATE).quantize(CENT, ROUND_HALF_UP)
    f.f507 = sum((p.base_zero for p in business), ZERO)
    f.f115 = len(business)
    f.f601 = max(f.f421 - f.f520, ZERO)
    f.f602 = max(f.f520 - f.f421, ZERO)
    f.f605, f.f606 = carried
    f.f609 = sum((w.iva for w in held), ZERO)
    due = f.f601
    purchase_credit = f.f602 + f.f605
    used = min(due, purchase_credit)
    due, f.f615 = due - used, purchase_credit - used
    retention_credit = f.f606 + f.f609
    used = min(due, retention_credit)
    due, f.f617 = due - used, retention_credit - used
    f.f620 = due
    return IvaMonth(
        person=person,
        month=m,
        sales=sales,
        purchases=purchases,
        withholdings=[
            WithholdingRow(
                w.issuer_name, w.number, w.issue_date, w.invoice_number, w.income_tax, w.iva
            )
            for w in held
        ],
        form=f,
        opening_month=None,
        unclassified=sum(1 for p in purchases if p.iva_use is None),
        income_tax_withheld=sum((w.income_tax for w in held), ZERO),
    )


def month(db: Session, person: str, m: date) -> IvaMonth:
    """The person's return for a month, carrying credit from the opening month on."""
    m = first(m)
    start = opening(db, person)
    carried = (ZERO, ZERO)
    notes = []
    if start is None or start[0] > m:
        notes.append(
            "Enter the credit carried in from your last return (fields 615 and 617) so the "
            "months chain correctly."
        )
        out = _one(db, person, m, carried)
    else:
        cur, carried = start[0], (start[1], start[2])
        while True:
            out = _one(db, person, cur, carried)
            if cur == m:
                break
            carried = (out.form.f615, out.form.f617)
            cur = add_months(cur, 1)
    out.opening_month = start[0] if start else None
    out.notes = notes
    return out


# ---------------------------------------------------------------- the accountant's workbook
def workbook(r: IvaMonth) -> bytes:
    """The month as the accountant's workbook: sales, purchases with credit and personal expenses
    (as SRI lists them), and the Form 104 figures."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = f"{r.month:%Y-%m}"
    bold = Font(bold=True)
    ws.append(
        [
            "RUC EMISOR",
            "RAZON SOCIAL EMISOR",
            "TIPO COMPROBANTE",
            "SERIE COMPROBANTE",
            "CLAVE ACCESO",
            "FECHA EMISION",
            "VALOR SIN IMPUESTOS",
            "IVA",
            "IMPORTE TOTAL",
            "RTE RTA",
            "RTE IVA",
        ]
    )
    for c in ws[1]:
        c.font = bold

    def title(text: str) -> None:
        ws.append([])
        ws.append([text])
        ws.cell(ws.max_row, 1).font = bold

    def total(rows: list[list[object]], cols: tuple[int, ...]) -> None:
        line: list[object] = [""] * 11
        line[0] = "TOTAL"
        for col in cols:
            line[col] = sum((Decimal(str(x[col] or 0)) for x in rows), ZERO)
        ws.append(line)
        for cell in ws[ws.max_row]:
            cell.font = bold

    title("VENTAS 15%")
    rows: list[list[object]] = [
        ["", s.buyer_name, "Factura", s.number, "", s.issue_date, s.base_taxed + s.base_zero,
         s.tax, s.total, s.income_tax_withheld or None, s.iva_withheld or None]
        for s in r.sales
    ]  # fmt: skip
    for x in rows:
        ws.append(x)
    total(rows, (6, 7, 8, 9, 10))
    for name, use in (("COMPRAS 15%", "business"), ("GASTOS PERSONALES", "personal")):
        title(name)
        rows = [
            [p.issuer_ruc, p.issuer_name, "Factura", p.number, p.access_key, p.issue_date,
             p.base_taxed + p.base_zero, p.tax, p.total, None, None]
            for p in r.purchases if p.iva_use == use
        ]  # fmt: skip
        for x in rows:
            ws.append(x)
        total(rows, (6, 7, 8))
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, date):
                c.number_format = "DD/MM/YYYY"
            elif isinstance(c.value, Decimal):
                c.number_format = "#,##0.00"
    f = r.form
    form = wb.create_sheet("Formulario 104")
    form.append(["Campo", "Descripción", "Valor"])
    for c in form[1]:
        c.font = bold
    for code, text, value in (
        ("401 / 411", "Ventas locales gravadas tarifa diferente de cero", f.f401),
        ("421", "IVA generado", f.f421),
        ("403 / 413", "Ventas tarifa 0%", f.f403),
        ("111", "Comprobantes de venta emitidos", f.f111),
        ("500 / 510", "Adquisiciones con derecho a crédito tributario", f.f500),
        ("520", "IVA en adquisiciones (crédito tributario)", f.f520),
        ("507 / 517", "Adquisiciones tarifa 0%", f.f507),
        ("115", "Comprobantes de venta recibidos", f.f115),
        ("499", "Total impuesto a liquidar en este mes", f.f421),
        ("564", "Crédito tributario aplicable en este período", f.f520),
        ("601", "Impuesto causado", f.f601),
        ("602", "Crédito tributario aplicable en este período", f.f602),
        ("605", "Saldo crédito tributario mes anterior: adquisiciones", f.f605),
        ("606", "Saldo crédito tributario mes anterior: retenciones", f.f606),
        ("609", "Retenciones en la fuente de IVA de este período", f.f609),
        ("615", "Saldo crédito tributario próximo mes: adquisiciones", f.f615),
        ("617", "Saldo crédito tributario próximo mes: retenciones", f.f617),
        ("620 / 902", "Total impuesto a pagar", f.f620),
    ):
        form.append([code, text, value])
        if isinstance(value, Decimal):
            form.cell(form.max_row, 3).number_format = "#,##0.00"
    form.column_dimensions["B"].width = 60
    ws.column_dimensions["B"].width = 45
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
