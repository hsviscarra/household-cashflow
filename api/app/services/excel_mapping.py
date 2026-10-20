"""How each row of the Cash Flow workbook maps to a transaction type and category (F2).

Keys are (block, group header or None, row label), normalized: lower case, no accents, single
spaces. A lookup tries the group-specific key first, then the block-wide one. Rows marked with a
review note are best guesses that Hernan confirms in the import preview.
"""

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Mapping:
    type: str  # income, expense, savings, debt_payment, fee_interest
    category: str  # "Group" or "Group/Subcategory", as seeded
    person: str | None = None
    country: str | None = None
    review: str | None = None


def norm(text: object) -> str:
    if not text:
        return ""
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def _m(
    type_: str,
    category: str,
    person: str | None = None,
    country: str | None = None,
    review: str | None = None,
) -> Mapping:
    return Mapping(type_, category, person, country, review)


CARD = "Transfers/Card Payment"
LOANS = "Savings & Debt/Loan Payments"

_INCOME: dict[str, Mapping] = {
    "lauren": _m("income", "Salary/Lauren", "Lauren"),
    "hernan": _m("income", "Salary/Hernan", "Hernan"),
    "office rent": _m("income", "Office Rent", "Joint", "EC"),
    # Tefy pays her share of Hernan's father's insurance into BofA for 6 or 12 months at a time.
    "tefy - seguro": _m("income", "Insurance Reimbursement", "Joint", "US"),
    "insurance rembolso": _m("income", "Insurance Reimbursement", "Joint", "EC"),
    "iess - maternity": _m("income", "Other Income", "Lauren", "EC"),
    # Consulting work for the Inter-American Development Bank and the London School of Economics.
    "idb": _m("income", "Other Income", "Hernan"),
    "lse": _m("income", "Other Income", "Hernan"),
    "tax return": _m("income", "Other Income", "Joint", "US"),
    "others": _m("income", "Other Income", "Joint"),
    # Loan money received (2022); repaid through the Office Loan expense row.
    "office loan": _m("income", "Other Income", "Joint", "EC"),
}

_EXPENSE: dict[str, Mapping] = {
    # Housing and loans
    "biess depo": _m("expense", "Housing/Mortgage BIESS", "Joint", "EC"),
    "iess": _m(
        "expense", "Housing/Mortgage BIESS", "Joint", "EC", "2021 'IESS': the BIESS mortgage?"
    ),
    "condo fee": _m("expense", "Housing/Condo Fee", "Joint", "EC"),
    "aliquota ofi": _m("expense", "Housing/Office Alícuota", "Joint", "EC"),
    # Security fee for the conjunto.
    "bellavista fee": _m("expense", "Housing", "Joint", "EC"),
    "house renovaciones": _m("expense", "Housing/Home Maintenance", "Joint", "EC"),
    "office loan": _m("debt_payment", LOANS, "Joint", "EC"),
    "biess car": _m("debt_payment", LOANS, "Joint", "EC"),
    "produbanco car": _m("debt_payment", LOANS, "Joint", "EC"),
    "iess lau": _m("debt_payment", LOANS, "Lauren", "EC"),
    "firstmark": _m("debt_payment", LOANS, "Lauren", "US"),  # Lauren's US student loan
    "nelnet": _m("debt_payment", LOANS, "Joint", "US"),
    "h student loan": _m("debt_payment", LOANS, "Hernan", "US"),
    "malu": _m("debt_payment", LOANS, "Joint"),  # loan
    "alex/estefy": _m("debt_payment", LOANS, "Joint"),  # loan
    "sobregiro": _m("debt_payment", LOANS, "Joint"),  # overdraft repayment
    # Card payments (cash view)
    "capital one": _m("debt_payment", CARD, "Joint", "US"),
    "rei": _m("debt_payment", CARD, "Joint", "US", "REI: a credit card payment? (not sure yet)"),
    "h's ec cc": _m("debt_payment", CARD, "Hernan", "EC"),
    "h's black cc": _m("debt_payment", CARD, "Hernan", "EC"),
    "h's black mastercard": _m("debt_payment", CARD, "Hernan", "EC"),
    "h's diners": _m("debt_payment", CARD, "Hernan", "EC"),
    "h - diners": _m("debt_payment", CARD, "Hernan", "EC"),
    "l's ec cc": _m("debt_payment", CARD, "Lauren", "EC"),
    "l - diners": _m("debt_payment", CARD, "Lauren", "EC"),
    "diners": _m("debt_payment", CARD, "Joint", "EC"),
    "prodo blck": _m("debt_payment", CARD, "Joint", "EC"),  # Produbanco Black card
    "laverix cc": _m("debt_payment", CARD, "Joint", "EC"),  # Banco del Pacifico card
    # Health
    "ecuasanitas": _m("expense", "Health/Insurance", "Hernan", "EC"),
    # Hernan's father's insurance, paid by transfer to him in Ecuador.
    "h&c seguro": _m("expense", "Health/Dad's Insurance", "Joint", "EC"),
    "bmi": _m("expense", "Health/Insurance", "Joint", "EC"),
    "doula": _m("expense", "Health/Doctors", "Lauren", "EC"),
    # Household, childcare, pets
    "empleada": _m("expense", "Household Staff/Empleada Salary", "Joint", "EC"),
    "empleada iess": _m("expense", "Household Staff/Empleada IESS", "Joint", "EC"),
    "cleaning": _m("expense", "Household Staff", "Joint", "EC"),
    "daycare": _m("expense", "Childcare/Daycare", "Joint", "EC"),
    "daycare lunch": _m("expense", "Childcare/Daycare Lunch", "Joint", "EC"),
    "killa gaudaria": _m("expense", "Pets/Pet Daycare", "Joint", "EC"),  # Killa, the dog
    "killa guarderia": _m("expense", "Pets/Pet Daycare", "Joint", "EC"),
    "donation - perros": _m("expense", "Donations", "Joint", "EC"),
    # Utilities and subscriptions
    "agua": _m("expense", "Utilities/Water", "Joint", "EC"),
    "electricity": _m("expense", "Utilities/Electricity", "Joint", "EC"),
    "phone": _m("expense", "Utilities/Phone/Internet", "Joint", "EC"),
    "phone bill": _m("expense", "Utilities/Phone/Internet", "Joint", "EC"),
    "tv bill": _m("expense", "Utilities/Phone/Internet", "Joint", "EC"),
    "netflix": _m("expense", "Subscriptions & Software/Media", "Joint"),
    # Transport, travel, other
    "fondo vial": _m("expense", "Transport/Vehicle", "Joint", "EC"),
    "amt": _m("expense", "Transport/Vehicle", "Joint", "EC"),
    "matricula vehiculo": _m("expense", "Transport/Vehicle", "Joint", "EC"),
    "matricula": _m("expense", "Transport/Vehicle", "Joint", "EC"),
    "travel": _m("expense", "Travel", "Joint"),
    "others": _m("expense", "Other Expenses", "Joint"),
    # Savings
    "interactive brokers": _m("savings", "Savings & Debt/Investing", "Hernan", "US"),
}

_GROUPED: dict[tuple[str, str, str], Mapping] = {
    ("expense", "health appointments", "hernan"): _m("expense", "Health/Doctors", "Hernan", "EC"),
    ("expense", "health appointments", "lauren"): _m("expense", "Health/Doctors", "Lauren", "EC"),
    ("expense", "health appointments", "matias"): _m("expense", "Health/Doctors", "Joint", "EC"),
    ("expense", "health appointments", "juli"): _m("expense", "Health/Doctors", "Joint", "EC"),
}

# Rows without a label in column A, keyed by (sheet, row): the label they stand for.
UNLABELED_ROWS: dict[tuple[str, int], str] = {("Cash Flow 2025", 30): "Phone"}


def lookup(block: str, group: str | None, label: str) -> Mapping | None:
    """block is 'income' or 'expense' (plan rows use the same mapping)."""
    key = norm(label)
    hit = _GROUPED.get((block, norm(group), key))
    if hit:
        return hit
    return (_INCOME if block == "income" else _EXPENSE).get(key)
