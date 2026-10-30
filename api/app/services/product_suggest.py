"""Claude's product-group suggestions for invoice lines no rule or keyword knows (F21, ADR-021).

Only product descriptions leave the server (e.g. "YOGURT TONI FRUTILLA 1L"), never the invoice's
issuer, amounts, dates or anyone's identification. Claude answers with JSON that must use one of
the fixed product groups. A suggestion is shown on the Purchases page as "suggested"; it counts in
the month's totals but becomes a rule only when a person confirms it.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PRODUCT_GROUPS, Invoice, InvoiceLine
from app.services.suggest import SuggestError, available

log = logging.getLogger(__name__)

MAX_PRODUCTS = 120  # per click
EFFORT: Final = "low"
MAX_TOKENS = 16000
__all__ = ["SuggestError", "available", "call_claude", "suggest_month"]

SYSTEM = (
    "You sort products from Ecuadorian supermarket, pharmacy and shop invoices into spending "
    "groups. Descriptions are Spanish and abbreviated (e.g. 'YOG TONI FRUT 1L' is yogurt, "
    "'DET DEJA 2KG' is detergent, 'PAN BLANCO' is bread). For each product id pick the single "
    "best group id. Use 'Services' for labor, fees or subscriptions and 'Other' only when nothing "
    "fits."
)


def call_claude(products: dict[str, str]) -> dict[str, str]:
    """{product_id: description} -> {product_id: group}. One request; replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    group_ids = {f"g{i}": g for i, g in enumerate(PRODUCT_GROUPS, start=1)}
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "enum": list(products)},
                        "group_id": {"type": "string", "enum": list(group_ids)},
                    },
                    "required": ["product_id", "group_id"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["groups"],
        "additionalProperties": False,
    }
    payload = {
        "groups": [{"id": gid, "name": g} for gid, g in group_ids.items()],
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
        items = json.loads(text)["groups"]
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Claude product groups unreadable: %s characters", len(text))
        raise SuggestError("Claude's answer could not be read.") from exc
    return {
        str(i["product_id"]): group_ids[str(i["group_id"])]
        for i in items
        if isinstance(i, dict) and str(i.get("group_id")) in group_ids
    }


def suggest_month(db: Session, month: date) -> int:
    """Suggest a group for the month's products without one. Returns how many products got one."""
    if not available():
        raise SuggestError("Claude suggestions are off (no ANTHROPIC_API_KEY).", 503)
    end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    lines = list(
        db.scalars(
            select(InvoiceLine)
            .join(Invoice)
            .where(
                Invoice.issue_date >= month,
                Invoice.issue_date < end,
                InvoiceLine.product_group.is_(None),
            )
        )
    )
    descriptions: dict[str, str] = {}
    for ln in lines:
        descriptions.setdefault(ln.product_key, ln.description)
    keys = list(descriptions)[:MAX_PRODUCTS]
    if not keys:
        return 0
    ids = {f"p{i}": k for i, k in enumerate(keys, start=1)}
    answer = call_claude({pid: descriptions[k] for pid, k in ids.items()})
    by_key = {ids[pid]: g for pid, g in answer.items() if pid in ids}
    for ln in lines:
        if ln.product_key in by_key:
            ln.product_group, ln.group_source = by_key[ln.product_key], "claude"
    db.commit()
    return len(by_key)
