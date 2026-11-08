"""Personal expense deductions (gastos personales, ADR-036): each person's deductible expenses
for a tax year, from the SRI invoices, against the cap their dependents (cargas familiares)
allow, and the 18% rebate.

Each invoice gets a person and one of SRI's six categories:
- person: the buyer named in INVOICE_BUYERS when the XML was read, else a person's choice, else
  the person on the card or bank line that paid it;
- category: a person's choice, else the issuer's rule, else the category of the line that paid
  it, else the products (mostly food, or mostly pharmacy), else none yet.

Amounts are the invoice's value before IVA (base imponible). Nothing here is filed with the SRI:
it projects the rebate and lists the numbers for the form and the annex."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GP_CATEGORIES,
    Category,
    GpIssuerRule,
    GpProfile,
    Invoice,
    InvoiceLine,
    Transaction,
)

ZERO = Decimal(0)
CENT = Decimal("0.01")
PEOPLE = ("Hernan", "Lauren")
RATE = Decimal("0.18")
# The basic family basket (canasta básica familiar) the SRI uses for each tax year.
CANASTA = {2026: Decimal("821.80")}
# How many baskets the deductible expenses may reach, by cargas familiares (5 or more: 20).
BASKETS = {0: 7, 1: 9, 2: 11, 3: 14, 4: 17}
CATASTROPHIC_BASKETS = 100

# SRI's six groups; the keys stay as the SRI names them, the labels are in English (ADR-045).
LABELS = {
    "vivienda": "Housing",
    "educacion": "Education, arts & culture",
    "salud": "Health",
    "alimentacion": "Food",
    "vestimenta": "Clothing",
    "turismo": "Domestic tourism",
}

# The paying line's category → SRI category. Only clear cases; the rest wait for a person.
BY_CATEGORY = {
    "Supermarket": "alimentacion",
    "Grocery Delivery": "alimentacion",
    "Restaurants & Cafés": "alimentacion",
    "Food Delivery": "alimentacion",
    "Daycare Lunch": "alimentacion",
    "Pet Food & Supplies": "alimentacion",
    "Doctors": "salud",
    "Labs & Imaging": "salud",
    "Pharmacy": "salud",
    "Hospital": "salud",
    "Dental": "salud",
    "Vet": "salud",
    "Health Insurance": "salud",
    "Daycare": "educacion",
    "Courses & Certifications": "educacion",
    "Books": "educacion",
    "Clothing": "vestimenta",
    "Lodging": "turismo",
    "Trip Activities & Food": "turismo",
    "Property Tax": "vivienda",
    "Groceries": "alimentacion",
    "Health": "salud",
}
FOOD = {
    "Meat & Fish",
    "Dairy & Eggs",
    "Fruit & Vegetables",
    "Bakery",
    "Pantry",
    "Snacks & Sweets",
    "Drinks",
    "Frozen & Ready Meals",
}
PHARMACY = {"Health & Pharmacy"}


class GastosError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def cap(year: int, cargas: int, catastrophic: bool) -> Decimal | None:
    """The most a person may deduct: the year's basket times its baskets; None when the year's
    basket isn't known yet."""
    basket = CANASTA.get(year)
    if basket is None:
        return None
    n = CATASTROPHIC_BASKETS if catastrophic else BASKETS.get(cargas, 20)
    return (basket * n).quantize(CENT)


@dataclass
class Row:
    invoice_id: int
    issue_date: date
    issuer_ruc: str
    issuer_name: str
    number: str
    subtotal: Decimal
    total: Decimal
    person: str | None
    person_source: str | None  # invoice, chosen, paid
    category: str | None
    category_source: str | None  # chosen, issuer, paid, products
    transaction_id: int | None
    paid_as: str | None = None
    category_id: int | None = (
        None  # the app category: chosen for the invoice, else the paying line's
    )
    category_path: str | None = None


def sri_group(paths: dict[int, tuple[str, str | None]], category_id: int) -> str:
    """The SRI group an app category counts in, or "none" (not deductible)."""
    name, group = paths.get(category_id, ("", None))
    return BY_CATEGORY.get(name) or BY_CATEGORY.get(group or "") or "none"


def _path(paths: dict[int, tuple[str, str | None]], category_id: int | None) -> str | None:
    if category_id is None or category_id not in paths:
        return None
    name, group = paths[category_id]
    return f"{group} / {name}" if group else name


def _paths(db: Session) -> dict[int, tuple[str, str | None]]:
    """category_id -> (its name, its group's name)."""
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    return {
        c.category_id: (c.name, cats[c.parent_id].name if c.parent_id in cats else None)
        for c in cats.values()
    }


def _by_products(db: Session, ids: list[int]) -> dict[int, str]:
    """invoice_id -> alimentacion / salud when most of it (by value) is food / pharmacy."""
    shares: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    totals: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for i in range(0, len(ids), 1000):
        rows = db.execute(
            select(InvoiceLine.invoice_id, InvoiceLine.product_group, InvoiceLine.subtotal).where(
                InvoiceLine.invoice_id.in_(ids[i : i + 1000])
            )
        )
        for inv_id, group, amount in rows:
            totals[inv_id] += amount
            kind = "alimentacion" if group in FOOD else "salud" if group in PHARMACY else "other"
            shares[inv_id][kind] += amount
    out: dict[int, str] = {}
    for inv_id, by in shares.items():
        if not totals[inv_id]:
            continue
        top = max(("alimentacion", "salud"), key=lambda k: by[k])
        if by[top] * 2 >= totals[inv_id]:
            out[inv_id] = top
    return out


def rows(db: Session, year: int) -> list[Row]:
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.issue_date >= date(year, 1, 1), Invoice.issue_date < date(year + 1, 1, 1)
            )
            .order_by(Invoice.issue_date.desc(), Invoice.invoice_id.desc())
        )
    )
    rules = {r.issuer_ruc: r.gp_category for r in db.scalars(select(GpIssuerRule))}
    paid_ids = [i.transaction_id for i in invoices if i.transaction_id]
    paid: dict[int, Transaction] = {}
    for i in range(0, len(paid_ids), 1000):
        for txn in db.scalars(
            select(Transaction).where(Transaction.transaction_id.in_(paid_ids[i : i + 1000]))
        ):
            paid[txn.transaction_id] = txn
    paths = _paths(db)
    products = _by_products(db, [i.invoice_id for i in invoices])
    out = []
    for inv in invoices:
        t = paid.get(inv.transaction_id or 0)
        name, group = (
            paths.get(t.category_id, (None, None)) if t and t.category_id else (None, None)
        )
        if inv.person:
            person, p_src = inv.person, "invoice"
        elif t is not None and t.person in PEOPLE:
            person, p_src = t.person, "paid"
        else:
            person, p_src = None, None
        category: str | None
        if inv.category_id is not None:
            category, c_src = sri_group(paths, inv.category_id), "chosen"
        elif inv.gp_category:
            category, c_src = inv.gp_category, "chosen"
        elif inv.issuer_ruc in rules:
            category, c_src = rules[inv.issuer_ruc], "issuer"
        elif name and (name in BY_CATEGORY or (group or "") in BY_CATEGORY):
            category, c_src = BY_CATEGORY.get(name) or BY_CATEGORY[group or ""], "paid"
        elif inv.invoice_id in products:
            category, c_src = products[inv.invoice_id], "products"
        else:
            category, c_src = None, None
        out.append(
            Row(
                inv.invoice_id,
                inv.issue_date,
                inv.issuer_ruc,
                inv.issuer_name,
                inv.number,
                inv.subtotal,
                inv.total,
                person,
                p_src,
                category,
                c_src,
                inv.transaction_id,
                f"{group} / {name}" if group and name else name,
                inv.category_id or (t.category_id if t else None),
                _path(paths, inv.category_id or (t.category_id if t else None)),
            )
        )
    return out


@dataclass
class CategoryTotal:
    category: str
    label: str
    invoices: int
    amount: Decimal


@dataclass
class PersonSummary:
    person: str
    cargas: int
    catastrophic: bool
    cap: Decimal | None
    total: Decimal
    deductible: Decimal
    rebate: Decimal
    by_category: list[CategoryTotal]
    to_classify: int
    not_deductible: int


@dataclass
class Summary:
    year: int
    canasta: Decimal | None
    rate: Decimal
    people: list[PersonSummary] = field(default_factory=list)
    unassigned: int = 0
    unassigned_amount: Decimal = ZERO


def profile(db: Session, person: str, year: int) -> GpProfile:
    return db.get(GpProfile, (person, year)) or GpProfile(
        person=person, year=year, cargas=0, catastrophic=False
    )


def summary(db: Session, year: int) -> Summary:
    all_rows = rows(db, year)
    out = Summary(year, CANASTA.get(year), RATE)
    for r in all_rows:
        if r.person is None:
            out.unassigned += 1
            out.unassigned_amount += r.subtotal
    for person in PEOPLE:
        mine = [r for r in all_rows if r.person == person]
        prof = profile(db, person, year)
        limit = cap(year, prof.cargas, prof.catastrophic)
        by = []
        for c in GP_CATEGORIES:
            these = [r for r in mine if r.category == c]
            by.append(
                CategoryTotal(c, LABELS[c], len(these), sum((r.subtotal for r in these), ZERO))
            )
        total = sum((b.amount for b in by), ZERO)
        deductible = min(total, limit) if limit is not None else total
        out.people.append(
            PersonSummary(
                person,
                prof.cargas,
                prof.catastrophic,
                limit,
                total,
                deductible,
                (deductible * RATE).quantize(CENT),
                by,
                sum(1 for r in mine if r.category is None),
                sum(1 for r in mine if r.category == "none"),
            )
        )
    return out


def choose(
    db: Session,
    invoice_id: int,
    user: str,
    *,
    set_person: bool = False,
    person: str | None = None,
    set_category: bool = False,
    category: str | None = None,
    set_app_category: bool = False,
    category_id: int | None = None,
    remember_issuer: bool = False,
) -> Invoice:
    """A person's choice of whose invoice it is and its category; with remember_issuer, every
    invoice from the same issuer without a choice of its own takes that category."""
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise GastosError(f"Invoice {invoice_id} not found.", 404)
    if set_person:
        if person is not None and person not in PEOPLE:
            raise GastosError(f"Person must be one of {', '.join(PEOPLE)}.")
        inv.person = person
    if set_app_category:
        # An app category (the same list as everywhere else); its SRI group follows from it.
        if category_id is not None and db.get(Category, category_id) is None:
            raise GastosError(f"Category {category_id} not found.")
        inv.category_id = category_id
        set_category = True
        category = None if category_id is None else sri_group(_paths(db), category_id)
    if set_category:
        if category is not None and category != "none" and category not in GP_CATEGORIES:
            raise GastosError(f"Unknown category {category}.")
        if not set_app_category:
            inv.category_id = None
        inv.gp_category = category
        if remember_issuer:
            if category is None:
                rule = db.scalars(
                    select(GpIssuerRule).where(GpIssuerRule.issuer_ruc == inv.issuer_ruc)
                ).first()
                if rule is not None:
                    db.delete(rule)
            else:
                rule = db.scalars(
                    select(GpIssuerRule).where(GpIssuerRule.issuer_ruc == inv.issuer_ruc)
                ).first()
                if rule is None:
                    db.add(
                        GpIssuerRule(
                            issuer_ruc=inv.issuer_ruc, gp_category=category, created_by=user[:320]
                        )
                    )
                else:
                    rule.gp_category = category
                inv.gp_category = None  # the rule decides, so changing it later moves this too
    db.commit()
    return inv


def set_profile(db: Session, person: str, year: int, cargas: int, catastrophic: bool) -> GpProfile:
    if person not in PEOPLE:
        raise GastosError(f"Person must be one of {', '.join(PEOPLE)}.")
    prof = db.get(GpProfile, (person, year))
    if prof is None:
        prof = GpProfile(person=person, year=year)
        db.add(prof)
    prof.cargas, prof.catastrophic = cargas, catastrophic
    db.commit()
    return prof


@dataclass
class IssuerLine:
    issuer_ruc: str
    issuer_name: str
    category: str
    invoices: int
    subtotal: Decimal
    total: Decimal


def by_issuer(db: Session, year: int, person: str) -> list[IssuerLine]:
    """One line per issuer and category for a person: the numbers the annex asks for."""
    acc: dict[tuple[str, str], IssuerLine] = {}
    for r in rows(db, year):
        if r.person != person or r.category in (None, "none"):
            continue
        assert r.category is not None
        key = (r.issuer_ruc, r.category)
        line = acc.get(key) or IssuerLine(r.issuer_ruc, r.issuer_name, r.category, 0, ZERO, ZERO)
        line.invoices += 1
        line.subtotal += r.subtotal
        line.total += r.total
        acc[key] = line
    return sorted(acc.values(), key=lambda x: (x.category, -x.subtotal))
