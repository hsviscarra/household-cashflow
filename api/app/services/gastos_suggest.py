"""Claude's SRI category for issuers nobody classified (ADR-081).

An invoice whose category for gastos personales can't be told from a person's choice, an issuer
rule, the line that paid it or its products waits on Taxes for someone. Most of those are plain:
a school is education, a clinic is health. Once a day (the Gmail script's check-in) Claude is asked
about the issuers still waiting, with each one's name and largest products, and an answer at or
above the autopilot threshold (ADR-029, 0.90) is saved as an issuer rule made by
"claude (automatic)". A person's choice on an invoice, or their own issuer rule, always wins.

Only the issuer's name (a business) and product descriptions leave the server."""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GP_CATEGORIES, GpIssuerRule, InvoiceLine
from app.services import gastos

log = logging.getLogger(__name__)

BY = gastos.CLAUDE
MAX_ISSUERS = 40
PRODUCTS = 5
CHOICES = (*GP_CATEGORIES, "none")

SYSTEM = (
    "You classify sellers on Ecuadorian electronic invoices for the income-tax deduction of "
    "personal expenses (gastos personales, SRI). For each seller, with its name and the largest "
    "products it sold this family, answer one category: vivienda (rent, mortgage interest, "
    "property tax, condominium fees, water, electricity, gas, landline), educacion (tuition, "
    "school transport and supplies, uniforms, books, child care, courses, arts and culture), "
    "salud (doctors, clinics, laboratories, pharmacy, health insurance, glasses), alimentacion "
    "(groceries, restaurants, food), vestimenta (clothing and shoes), turismo (hotels and "
    "tourism inside Ecuador), or none when it isn't deductible (electronics, fuel, vehicles, "
    "mobile phone and internet plans, entertainment, banks, furniture, general merchandise). "
    "Give a confidence from 0 to 1 and a reason of at most 12 words. Use a low confidence when "
    "the seller sells several kinds of things or the name and products don't make it clear."
)


@dataclass
class Asked:
    """An issuer Claude is asked about, with what it sells."""

    ruc: str
    name: str
    products: list[str]


@dataclass
class Answer:
    """Claude's deductible-expense kind for an issuer, with its confidence."""

    ruc: str
    category: str
    confidence: Decimal


@dataclass
class Done:
    """How many issuers were asked about and how many answers were kept."""

    asked: int = 0
    saved: int = 0


def waiting(db: Session, year: int) -> list[Asked]:
    """Issuers with an invoice this year that has no category yet, largest first."""
    rows = [r for r in gastos.rows(db, year) if r.category is None]
    ids: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for r in rows:
        ids[r.issuer_ruc].append(r.invoice_id)
        names[r.issuer_ruc] = r.issuer_name
        totals[r.issuer_ruc] += r.subtotal
    out = []
    for ruc in sorted(ids, key=lambda k: -totals[k])[:MAX_ISSUERS]:
        lines = db.execute(
            select(InvoiceLine.description, InvoiceLine.subtotal)
            .where(InvoiceLine.invoice_id.in_(ids[ruc][:200]))
            .order_by(InvoiceLine.subtotal.desc())
            .limit(PRODUCTS * 4)
        )
        seen: list[str] = []
        for description, _ in lines:
            if description not in seen:
                seen.append(description)
        out.append(Asked(ruc, names[ruc], seen[:PRODUCTS]))
    return out


def call_claude(asked: list[Asked]) -> list[Answer]:
    """One Messages API call with a JSON-schema answer. Replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    ids = {f"s{i}": a for i, a in enumerate(asked, start=1)}
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "sellers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": list(ids)},
                        "category": {"type": "string", "enum": list(CHOICES)},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "category", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["sellers"],
        "additionalProperties": False,
    }
    payload = {
        "sellers": [{"id": k, "name": a.name, "products": a.products} for k, a in ids.items()]
    }
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    out = []
    for item in json.loads(text).get("sellers", []):
        a = ids.get(str(item.get("id")))
        if a is None or item.get("category") not in CHOICES:
            continue
        out.append(Answer(a.ruc, item["category"], Decimal(str(item.get("confidence", 0)))))
    return out


def autopilot(db: Session, year: int) -> Done:
    """Ask about the issuers still waiting and save the sure answers as issuer rules. Never
    raises: a failure leaves the invoices waiting on Taxes, as before."""
    settings = get_settings()
    threshold = settings.auto_accept_confidence
    done = Done()
    if threshold <= 0 or not settings.anthropic_api_key:
        return done
    try:
        asked = waiting(db, year)
        if not asked:
            return done
        done.asked = len(asked)
        known = set(db.scalars(select(GpIssuerRule.issuer_ruc)))
        for a in call_claude(asked):
            if a.confidence < threshold or a.ruc in known:
                continue
            db.add(GpIssuerRule(issuer_ruc=a.ruc, gp_category=a.category, created_by=BY))
            known.add(a.ruc)
            done.saved += 1
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Tax categories: Claude didn't finish")
    return done
