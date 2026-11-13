"""What each grocery product is and who makes it (ADR-061): aisle, type and brand.

Claude labels products that have no label yet ("QSO MOZZ KIOSKO 500G" -> Dairy & Eggs, Cheese,
Kiosko); a person can correct any of the three, and that becomes the product's rule, applied to
every line with it now and on later invoices. Only product descriptions leave the server, as for
product groups (ADR-021).
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PRODUCT_GROUPS, InvoiceLine, ProductRule
from app.services import groceries
from app.services.recurring import add_months, first
from app.services.suggest import SuggestError, available

log = logging.getLogger(__name__)

MAX_PRODUCTS = 120  # per request
EFFORT: Final = "low"
MAX_TOKENS = 16000
ZERO = Decimal(0)
UNKNOWN = "Unknown"
__all__ = ["SuggestError", "available", "call_claude", "label", "products", "set_labels"]

SYSTEM = (
    "You label products from Ecuadorian supermarket invoices. Descriptions are Spanish and "
    "abbreviated (e.g. 'QSO MOZZ KIOSKO 500G' is mozzarella cheese by Kiosko, 'YOG TONI FRUT 1L' "
    "is yogurt by Toni, 'PECHUGA POLLO MR POLLO KG' is chicken by Mr. Pollo, 'PAN BLANCO' is "
    "bread with no brand). For each product id give: the best aisle id; the type of product as a "
    "short, general English noun used across brands (Cheese, Yogurt, Milk, Chicken, Beef, Rice, "
    "Bread, Apples, Detergent, Diapers, Coffee); and the brand as printed (capitalized, e.g. "
    "Kiosko, Toni, Mr. Pollo, Supermaxi), or an empty string when there is none (produce, meat by "
    "weight, bakery). Store brands count as brands."
)


def call_claude(products: dict[str, str]) -> dict[str, tuple[str, str, str]]:
    """{product_id: description} -> {product_id: (group, type, brand)}. Replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=90)
    group_ids = {f"g{i}": g for i, g in enumerate(PRODUCT_GROUPS, start=1)}
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "enum": list(products)},
                        "group_id": {"type": "string", "enum": list(group_ids)},
                        "type": {"type": "string"},
                        "brand": {"type": "string"},
                    },
                    "required": ["product_id", "group_id", "type", "brand"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["labels"],
        "additionalProperties": False,
    }
    payload = {
        "aisles": [{"id": gid, "name": g} for gid, g in group_ids.items()],
        "products": [{"id": pid, "description": d} for pid, d in products.items()],
    }
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIError as exc:
        raise SuggestError(f"Claude could not be reached: {exc.__class__.__name__}.") from exc
    if getattr(response, "stop_reason", None) in ("max_tokens", "refusal"):
        raise SuggestError("Claude's answer was cut off or declined; try again.")
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        items = json.loads(text)["labels"]
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Claude product labels unreadable: %s characters", len(text))
        raise SuggestError("Claude's answer could not be read.") from exc
    out: dict[str, tuple[str, str, str]] = {}
    for i in items:
        if not isinstance(i, dict) or str(i.get("group_id")) not in group_ids:
            continue
        out[str(i["product_id"])] = (
            group_ids[str(i["group_id"])],
            _clean(i.get("type")),
            _clean(i.get("brand")),
        )
    return out


def _clean(v: object) -> str:
    return " ".join(str(v or "").split())[:60]


def _lines(db: Session, start: date, months: int) -> list[InvoiceLine]:
    """The supermarket invoices' lines from `start` for `months` months."""
    m = first(start)
    end = add_months(m, months)
    gid = groceries._group_id(db)
    txns = groceries._grocery_txns(db, gid, add_months(m, -1), end)
    return [ln for inv in groceries._invoices(db, m, end, txns) for ln in inv.lines]


def label(db: Session, start: date, months: int = 1) -> int:
    """Ask Claude for the products without a type yet. Returns how many products got labels."""
    if not available():
        raise SuggestError("Claude suggestions are off (no ANTHROPIC_API_KEY).", 503)
    lines = [ln for ln in _lines(db, start, months) if ln.label_source is None]
    descriptions: dict[str, str] = {}
    for ln in lines:
        descriptions.setdefault(ln.product_key, ln.description)
    keys = list(descriptions)[:MAX_PRODUCTS]
    if not keys:
        return 0
    ids = {f"p{i}": k for i, k in enumerate(keys, start=1)}
    answer = call_claude({pid: descriptions[k] for pid, k in ids.items()})
    by_key = {ids[pid]: v for pid, v in answer.items() if pid in ids}
    for ln in db.scalars(select(InvoiceLine).where(InvoiceLine.product_key.in_(list(by_key)))):
        if ln.label_source == "confirmed":
            continue
        group, kind, brand = by_key[ln.product_key]
        ln.product_type, ln.brand, ln.label_source = kind or None, brand or None, "claude"
        if ln.product_group is None:
            ln.product_group, ln.group_source = group, "claude"
    db.commit()
    return len(by_key)


LABELS = ("product_group", "product_type", "brand")
USER_MAX = 320  # the width of created_by


def _apply(rule: ProductRule, lines: list[InvoiceLine], changes: dict[str, str | None]) -> None:
    """Write the changed labels on the rule and on every line of the product."""
    for col in LABELS:
        if col not in changes:
            continue
        value = _clean(changes[col]) or None
        setattr(rule, col, value)
        for ln in lines:
            setattr(ln, col, value)
            if col == "product_group":
                ln.group_source = "confirmed" if value else None


def set_labels(db: Session, key: str, changes: dict[str, str | None], user: str) -> int:
    """A person's aisle, type or brand for a product: kept as its rule and set on every line with
    it. Returns how many lines changed."""
    group = changes.get("product_group")
    if group is not None and group not in PRODUCT_GROUPS:
        raise SuggestError(f"Unknown aisle {group!r}.", 422)
    rule = db.scalar(select(ProductRule).where(ProductRule.product_key == key))
    if rule is None:
        rule = ProductRule(product_key=key, created_by=user[:USER_MAX])
        db.add(rule)
    lines = list(db.scalars(select(InvoiceLine).where(InvoiceLine.product_key == key)))
    if not lines:
        raise SuggestError(f"No purchases of {key!r}.", 404)
    _apply(rule, lines, changes)
    # The rest of the labels Claude gave become the person's too, once they've looked at them.
    for col in ("product_type", "brand"):
        if col not in changes and getattr(rule, col) is None:
            setattr(rule, col, getattr(lines[0], col))
    for ln in lines:
        ln.product_type, ln.brand, ln.label_source = rule.product_type, rule.brand, "confirmed"
    rule.created_by = user[:USER_MAX]
    db.commit()
    return len(lines)


@dataclass
class Product:
    """A product from the invoices with its group, type and brand."""

    product_key: str
    description: str
    product_group: str | None
    product_type: str | None
    brand: str | None
    label_source: str | None
    times: int
    quantity: Decimal
    amount: Decimal
    unit_price: Decimal
    stores: list[str]


@dataclass
class Total:
    """An amount for a group, type or brand."""

    name: str
    amount: Decimal
    products: int


@dataclass
class ProductList:
    """The products bought over some months, with totals by group, type and brand."""

    start: date
    months: int
    total: Decimal
    products: list[Product]
    by_group: list[Total] = field(default_factory=list)
    by_type: list[Total] = field(default_factory=list)
    by_brand: list[Total] = field(default_factory=list)
    unlabeled: int = 0


def _totals(rows: list[Product], attr: str) -> list[Total]:
    acc: dict[str, list[Any]] = defaultdict(lambda: [ZERO, 0])
    for p in rows:
        name = getattr(p, attr) or UNKNOWN
        acc[name][0] += p.amount
        acc[name][1] += 1
    return sorted(
        (Total(n, a, c) for n, (a, c) in acc.items()), key=lambda t: (t.name == UNKNOWN, -t.amount)
    )


def products(db: Session, start: date, months: int = 1) -> ProductList:
    """Every supermarket product bought in the period, biggest first, with totals by aisle, type
    and brand."""
    acc: dict[str, list[InvoiceLine]] = defaultdict(list)
    for ln in _lines(db, start, months):
        acc[ln.product_key].append(ln)
    rows = []
    for key, lines in acc.items():
        qty = sum((ln.quantity or Decimal(1) for ln in lines), ZERO)
        amount = sum((ln.total for ln in lines), ZERO).quantize(Decimal("0.01"))
        last = lines[-1]
        rows.append(
            Product(
                product_key=key,
                description=last.description,
                product_group=last.product_group,
                product_type=last.product_type,
                brand=last.brand,
                label_source=last.label_source,
                times=len(lines),
                quantity=qty,
                amount=amount,
                unit_price=(amount / qty).quantize(Decimal("0.01")) if qty else amount,
                stores=sorted({ln.invoice.issuer_name for ln in lines}),
            )
        )
    rows.sort(key=lambda p: (-p.amount, p.description))
    return ProductList(
        start=first(start),
        months=months,
        total=sum((p.amount for p in rows), ZERO),
        products=rows,
        by_group=_totals(rows, "product_group"),
        by_type=_totals(rows, "product_type"),
        by_brand=_totals(rows, "brand"),
        unlabeled=sum(1 for p in rows if p.label_source is None),
    )
