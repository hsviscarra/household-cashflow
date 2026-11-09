"""Purchases from electronic invoices (F21, ADR-021): a month's invoices with their products, the
spending by product group, and the products still to group."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.models import PRODUCT_GROUPS, Account, Category, Invoice, Transaction
from app.schemas import (
    GroupTotalOut,
    InvoiceLineOut,
    InvoiceOut,
    InvoiceUploadOut,
    PaidWithOut,
    ProductGroupIn,
    ProductGroupOut,
    PurchasesOut,
    SuggestedOut,
    UngroupedOut,
)
from app.services import invoices, iva, product_suggest, sri

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
DB = Annotated[Session, Depends(get_session)]
MAX_FILES = 100
SRI_BATCH = 10
ZERO = Decimal(0)


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _month(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError as exc:
        raise HTTPException(422, "Months look like 2026-10.") from exc


def receive_xml(db: Session, data: bytes, file_name: str, user: str) -> InvoiceUploadOut:
    """One XML file, from the inbox or an upload: stored, duplicate, skipped or refused."""
    name = (file_name or "invoice.xml")[:260]
    try:  # an invoice the household issued goes to the IVA return, not to purchases (ADR-062)
        sale = iva.own_sale(data) if len(data) <= invoices.MAX_BYTES else None
    except invoices.InvoiceError:
        sale = None
    if sale is not None:
        s, dup = iva.store_sale(db, sale, user)
        return InvoiceUploadOut(
            file_name=name,
            outcome="duplicate" if dup else "stored",
            message=f"Your invoice {s.number} to {s.buyer_name}: {s.total:,.2f}"
            + (" is already in the app." if dup else ", for the IVA return."),
        )
    try:
        parsed = invoices.parse(data)
    except invoices.NotAnInvoice as exc:
        try:
            n = iva.note(data)
        except invoices.InvoiceError:
            n = None
        if n is not None:
            saved, dup = iva.store_note(db, n, user)
            word = "Nota de crédito" if saved.kind == "credit" else "Nota de débito"
            return InvoiceUploadOut(
                file_name=name,
                outcome="duplicate" if dup else "stored",
                message=f"{word} {saved.number} ({saved.issuer_name}): {saved.total:,.2f}"
                + (" is already in the app." if dup else ", for the IVA return."),
            )
        try:
            held = iva.withholding(data)
        except invoices.InvoiceError:
            held = None
        if held is not None:
            w, dup = iva.store_withholding(db, held, user)
            return InvoiceUploadOut(
                file_name=name,
                outcome="duplicate" if dup else "stored",
                message=f"Retención {w.number} from {w.issuer_name}: income tax "
                f"{w.income_tax:,.2f}, IVA {w.iva:,.2f}"
                + (" is already in the app." if dup else "."),
            )
        return InvoiceUploadOut(file_name=name, outcome="skipped", message=str(exc))
    except invoices.InvoiceError as exc:
        return InvoiceUploadOut(file_name=name, outcome="rejected", message=str(exc))
    stored = invoices.store(db, parsed, user)
    inv = stored.invoice
    if stored.duplicate:
        return InvoiceUploadOut(
            file_name=name,
            outcome="duplicate",
            message=f"Invoice {inv.number} is already in the app.",
            invoice_id=inv.invoice_id,
        )
    paid = "matched to its payment" if inv.transaction_id else "its payment isn't loaded yet"
    return InvoiceUploadOut(
        file_name=name,
        outcome="stored",
        message=f"{inv.issuer_name}: {len(inv.lines)} products, {inv.total}; {paid}.",
        invoice_id=inv.invoice_id,
    )


@router.post("", response_model=list[InvoiceUploadOut])
async def upload(files: list[UploadFile], request: Request, db: DB) -> list[InvoiceUploadOut]:
    """Invoice XMLs downloaded from SRI en línea or from a vendor's email."""
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Upload at most {MAX_FILES} files at a time.")
    out = []
    for f in files:
        data = await f.read(invoices.MAX_BYTES + 1)
        out.append(receive_xml(db, data, f.filename or "", _user(request)))
    return out


class SriTextIn(BaseModel):
    text: str = Field(max_length=5_000_000)


class SriKeysOut(BaseModel):
    new: list[str]
    stored: int
    other: int


class SriFetchIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=SRI_BATCH)


@router.post("/sri/keys", response_model=SriKeysOut)
def sri_keys(body: SriTextIn, db: DB) -> SriKeysOut:
    """The access keys in an SRI "Comprobantes recibidos" report (or any pasted text): invoices
    not in the app yet, invoices already here, and other documents (ADR-037)."""
    k = sri.find_keys(db, body.text)
    return SriKeysOut(new=k.new, stored=k.stored, other=k.other)


@router.post("/sri/fetch", response_model=list[InvoiceUploadOut])
def sri_fetch(body: SriFetchIn, request: Request, db: DB) -> list[InvoiceUploadOut]:
    """Up to 10 access keys at a time: each invoice's authorized XML from the SRI, read and stored
    like an upload. The page sends the keys in batches so each request stays short."""
    out = []
    for key in body.keys:
        if not sri.KEY.fullmatch(key):
            out.append(
                InvoiceUploadOut(
                    file_name=key[:60], outcome="rejected", message="Not an access key."
                )
            )
            continue
        try:
            answer = sri.fetch(key)
        except sri.SriError as exc:
            out.append(InvoiceUploadOut(file_name=key, outcome="rejected", message=str(exc)))
            continue
        if answer.xml is None:
            words = {
                "NONE": "The SRI has no document with this access key.",
                "NO AUTORIZADO": "The SRI didn't authorize this document.",
                "EN PROCESAMIENTO": "The SRI is still processing it; try again later.",
            }
            out.append(
                InvoiceUploadOut(
                    file_name=key,
                    outcome="rejected",
                    message=words.get(answer.state, f"The SRI answered {answer.state}.")
                    + (f" {answer.reason}" if answer.reason else ""),
                )
            )
            continue
        out.append(receive_xml(db, answer.xml, key, _user(request)))
    return out


def _paid_with(db: Session, inv: Invoice) -> PaidWithOut | None:
    if inv.transaction_id is None:
        return None
    t = db.get(Transaction, inv.transaction_id)
    if t is None:
        return None
    acct = db.get(Account, t.account_id) if t.account_id else None
    return PaidWithOut(
        transaction_id=t.transaction_id,
        txn_date=t.txn_date,
        account=acct.name if acct else None,
        description=t.description_raw,
    )


def _category_paths(db: Session) -> dict[int, str]:
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    return {
        cid: f"{cats[c.parent_id].name} / {c.name}" if c.parent_id in cats else c.name
        for cid, c in cats.items()
    }


@router.get("", response_model=PurchasesOut)
def purchases(month: str, db: DB) -> PurchasesOut:
    """A month of invoices (by invoice date): products, groups, and what's left to group."""
    m = _month(month)
    invoices.link_pending(db, since=date(m.year - 1, m.month, 1))
    invs = invoices.month_invoices(db, m)
    to_group: dict[str, UngroupedOut] = {}
    paths = _category_paths(db)
    for inv in invs:
        for ln in inv.lines:
            if ln.group_source in ("confirmed", "rule") or ln.category_id is not None:
                continue
            u = to_group.setdefault(
                ln.product_key,
                UngroupedOut(
                    product_key=ln.product_key,
                    description=ln.description,
                    lines=0,
                    amount=ZERO,
                    suggested_group=ln.product_group,
                ),
            )
            u.lines += 1
            u.amount += ln.total
    return PurchasesOut(
        month=month,
        total=sum((i.total for i in invs), ZERO),
        matched_total=sum((i.total for i in invs if i.transaction_id), ZERO),
        groups=[
            GroupTotalOut(group=g.group, amount=g.amount, lines=g.lines)
            for g in invoices.month_groups(db, m)
        ],
        to_group=sorted(to_group.values(), key=lambda u: (-u.amount, u.description)),
        invoices=[
            InvoiceOut(
                invoice_id=i.invoice_id,
                issuer_name=i.issuer_name,
                number=i.number,
                issue_date=i.issue_date,
                subtotal=i.subtotal,
                tax=i.tax,
                total=i.total,
                received_by=i.received_by,
                paid_with=_paid_with(db, i),
                lines=[
                    InvoiceLineOut(
                        line_no=ln.line_no,
                        description=ln.description,
                        product_key=ln.product_key,
                        quantity=ln.quantity,
                        unit_price=ln.unit_price,
                        total=ln.total,
                        product_group=ln.product_group,
                        group_source=ln.group_source,
                        category_id=ln.category_id,
                        category_path=paths.get(ln.category_id) if ln.category_id else None,
                    )
                    for ln in i.lines
                ],
            )
            for i in invs
        ],
        product_groups=list(PRODUCT_GROUPS),
        suggestions_available=product_suggest.available(),
    )


@router.put("/products", response_model=ProductGroupOut)
def set_group(body: ProductGroupIn, request: Request, db: DB) -> ProductGroupOut:
    """A product's group or app category, for every invoice it's on, now and later."""
    sent = body.model_fields_set
    try:
        if "category_id" in sent:
            n = invoices.confirm_category(db, body.product_key, body.category_id, _user(request))
        elif body.product_group:
            n = invoices.confirm(db, body.product_key, body.product_group, _user(request))
        else:
            raise HTTPException(422, "Send product_group or category_id.")
    except invoices.InvoiceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ProductGroupOut(
        product_key=body.product_key,
        product_group=body.product_group,
        category_id=body.category_id,
        lines_updated=n,
    )


@router.post("/suggest", response_model=SuggestedOut)
def suggest(month: str, db: DB) -> SuggestedOut:
    """Claude's group for the month's products without one (only descriptions are sent)."""
    try:
        return SuggestedOut(products=product_suggest.suggest_month(db, _month(month)))
    except product_suggest.SuggestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
