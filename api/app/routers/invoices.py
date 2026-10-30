"""Purchases from electronic invoices (F21, ADR-021): a month's invoices with their products, the
spending by product group, and the products still to group."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.models import PRODUCT_GROUPS, Account, Invoice, Transaction
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
from app.services import invoices, product_suggest

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
DB = Annotated[Session, Depends(get_session)]
MAX_FILES = 100
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
    try:
        parsed = invoices.parse(data)
    except invoices.NotAnInvoice as exc:
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


@router.get("", response_model=PurchasesOut)
def purchases(month: str, db: DB) -> PurchasesOut:
    """A month of invoices (by invoice date): products, groups, and what's left to group."""
    m = _month(month)
    invoices.link_pending(db, since=date(m.year - 1, m.month, 1))
    invs = invoices.month_invoices(db, m)
    to_group: dict[str, UngroupedOut] = {}
    for inv in invs:
        for ln in inv.lines:
            if ln.group_source in ("confirmed", "rule"):
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
    """A product's group, for every invoice it's on, now and later."""
    try:
        n = invoices.confirm(db, body.product_key, body.product_group, _user(request))
    except invoices.InvoiceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ProductGroupOut(
        product_key=body.product_key, product_group=body.product_group, lines_updated=n
    )


@router.post("/suggest", response_model=SuggestedOut)
def suggest(month: str, db: DB) -> SuggestedOut:
    """Claude's group for the month's products without one (only descriptions are sent)."""
    try:
        return SuggestedOut(products=product_suggest.suggest_month(db, _month(month)))
    except product_suggest.SuggestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
