"""Claude's category suggestions for merchants no rule knows (F9, ADR-006).

Only what is needed leaves the server: each merchant's description as printed, amounts, dates and
the bank's name and country. No account numbers, no names of people, no balances. Claude answers
with JSON that must follow a schema whose category is one of Hernan's own category paths, plus a
confidence from 0 to 1 and a short reason. Suggestions are stored and shown in the review queue;
nothing is categorized until Hernan accepts one.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.preview import category_paths
from app.models import Account, Category, MerchantSuggestion, Transaction
from app.services import classify

MAX_MERCHANTS = 40  # per request; a month rarely has more unknown merchants
SAMPLES = 3  # lines shown per merchant

SYSTEM = (
    "You categorize household bank and credit card transactions for a family in Quito, Ecuador, "
    "that also has US accounts. Amounts are USD; negative means money out. For each merchant, "
    "pick the single best category path from the list given, a confidence from 0 to 1 (how sure "
    "you are this merchant belongs there), and a reason of at most 15 words. Use a low confidence "
    "when the description is ambiguous (for example a bare bank transfer). Spanish descriptions "
    "are common: TRANSFERENCIA = transfer, DEBITO = debit, PAGO = payment, CONSUMO = purchase."
)


class SuggestError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def available() -> bool:
    return bool(get_settings().anthropic_api_key)


@dataclass
class Asked:
    merchant_key: str
    lines: list[dict[str, Any]]


@dataclass
class Answer:
    merchant_key: str
    category_path: str
    confidence: Decimal
    reason: str


def _schema(paths: list[str], keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "merchant_key": {"type": "string", "enum": keys},
                        "category_path": {"type": "string", "enum": paths},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["merchant_key", "category_path", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["suggestions"],
        "additionalProperties": False,
    }


def call_claude(asked: list[Asked], categories: list[str]) -> list[Answer]:
    """One Messages API call with a JSON-schema answer. Replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    payload = {
        "categories": categories,
        "merchants": [{"merchant_key": a.merchant_key, "lines": a.lines} for a in asked],
    }
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _schema(categories, [a.merchant_key for a in asked]),
                }
            },
        )
    except anthropic.APIError as exc:
        raise SuggestError(f"Claude could not be reached: {exc.__class__.__name__}.") from exc
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        items = json.loads(text)["suggestions"]
        return [
            Answer(
                i["merchant_key"],
                i["category_path"],
                Decimal(str(i["confidence"])),
                str(i["reason"]),
            )
            for i in items
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise SuggestError("Claude's answer could not be read.") from exc


def suggest(db: Session, month: date | None = None) -> tuple[int, int]:
    """Ask Claude about the uncategorized merchants that have no suggestion yet.
    Returns (merchants asked, suggestions stored)."""
    if not available():
        raise SuggestError("Suggestions are off: set ANTHROPIC_API_KEY on the server.", 503)
    groups = [g for g in classify.review_groups(db, month) if g.suggestion is None]
    groups = groups[:MAX_MERCHANTS]
    if not groups:
        return 0, 0

    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    ids = [ln.transaction_id for g in groups for ln in g.lines]
    rows = {
        t.transaction_id: t
        for t in db.scalars(select(Transaction).where(Transaction.transaction_id.in_(ids)))
    }
    asked = []
    for g in groups:
        lines = []
        for ln in g.lines[:SAMPLES]:
            account = accounts.get(rows[ln.transaction_id].account_id or -1)
            lines.append(
                {
                    "description": ln.description,
                    "amount": str(ln.amount),
                    "date": ln.txn_date.isoformat(),
                    "bank": account.institution if account else None,
                    "country": account.country if account else None,
                    "card_or_account": account.kind if account else None,
                }
            )
        asked.append(Asked(g.merchant_key, lines))

    paths = category_paths(db)
    by_path = {p: cid for cid, p in paths.items()}
    # Groups only (no subcategories) are offered when they have no children.
    parents = {c.parent_id for c in db.scalars(select(Category)) if c.parent_id is not None}
    offered = sorted(p for cid, p in paths.items() if cid not in parents)

    answers = call_claude(asked, offered)
    keys = {a.merchant_key for a in asked}
    model = get_settings().anthropic_model
    stored = 0
    for a in answers:
        cid = by_path.get(a.category_path)
        if a.merchant_key not in keys or cid is None:
            continue  # the schema prevents this; never trust it blindly
        confidence = min(max(a.confidence, Decimal(0)), Decimal(1)).quantize(Decimal("0.001"))
        existing = db.scalar(
            select(MerchantSuggestion).where(MerchantSuggestion.merchant_key == a.merchant_key)
        )
        if existing is None:
            existing = MerchantSuggestion(merchant_key=a.merchant_key)
            db.add(existing)
        existing.category_id = cid
        existing.confidence = confidence
        existing.reason = a.reason[:400]
        existing.model = model
        stored += 1
    db.commit()
    return len(asked), stored
