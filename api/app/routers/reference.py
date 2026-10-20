"""Reference data: accounts, categories and merchant rules (F1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Account, Category, MerchantRule
from app.schemas import (
    AccountIn,
    AccountOut,
    AccountPatch,
    CategoryGroup,
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    RuleIn,
    RuleOut,
    RulePatch,
    RuleTestOut,
)
from app.services import rules as rule_engine

router = APIRouter(prefix="/api", tags=["reference"])
DB = Annotated[Session, Depends(get_session)]


def _commit(db: Session, conflict: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict) from exc


def _get[T](db: Session, model: type[T], key: int, label: str) -> T:
    obj = db.get(model, key)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} {key} not found.")
    return obj


# ---------------- accounts ----------------
@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: DB) -> list[Account]:
    return list(db.scalars(select(Account).order_by(Account.country.desc(), Account.name)))


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, db: DB) -> Account:
    account = Account(**body.model_dump())
    db.add(account)
    _commit(db, f"An account named {body.name!r} already exists.")
    return account


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountPatch, db: DB) -> Account:
    account = _get(db, Account, account_id, "Account")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    _commit(db, "Another account already has that name.")
    return account


# ---------------- categories ----------------
@router.get("/categories", response_model=list[CategoryGroup])
def list_categories(db: DB) -> list[CategoryGroup]:
    rows = list(db.scalars(select(Category).order_by(Category.sort_order, Category.name)))
    groups = [r for r in rows if r.parent_id is None]
    return [
        CategoryGroup(
            **CategoryOut.model_validate(g).model_dump(),
            children=[CategoryOut.model_validate(c) for c in rows if c.parent_id == g.category_id],
        )
        for g in groups
    ]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, db: DB) -> Category:
    if body.parent_id is None:
        if body.kind is None:
            raise HTTPException(422, "A new group needs a kind.")
        kind: str = body.kind
        siblings = select(Category).where(Category.parent_id.is_(None))
    else:
        parent = _get(db, Category, body.parent_id, "Category")
        if parent.parent_id is not None:
            raise HTTPException(
                422,
                "Subcategories go one level deep: pick a group as the parent.",
            )
        kind = parent.kind
        siblings = select(Category).where(Category.parent_id == parent.category_id)
    order = len(list(db.scalars(siblings)))
    category = Category(
        name=body.name,
        parent_id=body.parent_id,
        kind=kind,
        color=body.color,
        is_fixed=body.is_fixed,
        sort_order=order,
    )
    db.add(category)
    _commit(db, f"{body.name!r} already exists there.")
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryPatch, db: DB) -> Category:
    category = _get(db, Category, category_id, "Category")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    _commit(db, "A category with that name already exists there.")
    return category


# ---------------- merchant rules ----------------
def _paths(db: Session) -> dict[int, str]:
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    out: dict[int, str] = {}
    for cid, c in cats.items():
        parent = cats.get(c.parent_id) if c.parent_id is not None else None
        out[cid] = f"{parent.name} / {c.name}" if parent else c.name
    return out


def _rule_out(rule: MerchantRule, paths: dict[int, str]) -> RuleOut:
    return RuleOut(
        rule_id=rule.rule_id,
        pattern=rule.pattern,
        match_type=rule.match_type,  # type: ignore[arg-type]
        category_id=rule.category_id,
        category_path=paths.get(rule.category_id, "?"),
        priority=rule.priority,
        is_active=rule.is_active,
    )


def _check_rule(db: Session, pattern: str | None, match_type: str, category_id: int | None) -> None:
    if pattern is not None:
        error = rule_engine.validate_pattern(pattern, match_type)
        if error:
            raise HTTPException(422, error)
    if category_id is not None:
        _get(db, Category, category_id, "Category")


@router.get("/merchant-rules", response_model=list[RuleOut])
def list_rules(db: DB) -> list[RuleOut]:
    paths = _paths(db)
    rules = db.scalars(select(MerchantRule).order_by(MerchantRule.priority, MerchantRule.rule_id))
    return [_rule_out(r, paths) for r in rules]


@router.post("/merchant-rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, db: DB) -> RuleOut:
    _check_rule(db, body.pattern, body.match_type, body.category_id)
    rule = MerchantRule(**body.model_dump())
    db.add(rule)
    _commit(db, "Could not save the rule.")
    return _rule_out(rule, _paths(db))


@router.patch("/merchant-rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RulePatch, db: DB) -> RuleOut:
    rule = _get(db, MerchantRule, rule_id, "Rule")
    changes = body.model_dump(exclude_unset=True)
    _check_rule(
        db,
        changes.get("pattern", rule.pattern),
        changes.get("match_type", rule.match_type),
        changes.get("category_id"),
    )
    for field, value in changes.items():
        setattr(rule, field, value)
    _commit(db, "Could not save the rule.")
    return _rule_out(rule, _paths(db))


@router.delete("/merchant-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: DB) -> Response:
    rule = _get(db, MerchantRule, rule_id, "Rule")
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/merchant-rules/test", response_model=RuleTestOut)
def test_rules(db: DB, description: Annotated[str, Query(min_length=1)]) -> RuleTestOut:
    rows = list(db.scalars(select(MerchantRule)))
    candidates = [
        rule_engine.Rule(r.rule_id, r.pattern, r.match_type, r.category_id, r.priority, r.is_active)
        for r in rows
    ]
    hit = rule_engine.first_match(candidates, description)
    if hit is None:
        return RuleTestOut(description=description, rule=None)
    match = next(r for r in rows if r.rule_id == hit.rule_id)
    return RuleTestOut(description=description, rule=_rule_out(match, _paths(db)))
