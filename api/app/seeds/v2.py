"""Seed v2 (F2): categories the Excel history needs. Frozen like v1.

(group, kind, color for a new group or None for an existing one, [(subcategory, is_fixed)])
"""

CATEGORIES: list[tuple[str, str, str | None, list[tuple[str, bool]]]] = [
    ("Health", "expense", None, [("Dad's Insurance", True)]),
    ("Savings & Debt", "savings", None, [("Loan Payments", True)]),
    ("Pets", "expense", "#5C8A8A", [("Pet Daycare", False)]),
    ("Other Expenses", "expense", "#78716C", []),
]
