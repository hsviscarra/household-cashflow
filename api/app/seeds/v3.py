"""Seed v3 (F8b): the Banco del Pacífico Mastercard (Pacificard) and rules for its charges.
Frozen like v1 and v2: change seeds with a new version, never by editing this one.
"""

# Pacificard prints the card as NNNN-NNXX-XXXX-XNNN: only three digits, so no last4 is kept and
# the statement is matched as the issuer's only account (Pacificard is Banco del Pacífico's card
# issuer; the bank's own accounts are a separate institution).
ACCOUNTS: list[dict[str, str | None]] = [
    {
        "name": "Pacificard Mastercard Black",
        "institution": "Pacificard",
        "kind": "credit_card",
        "owner": "Hernan",
        "country": "EC",
        "last4": None,
    },
]

# (pattern, match_type, "Group/Sub", priority)
MERCHANT_RULES: list[tuple[str, str, str, int]] = [
    ("FINANC.SOLCA", "contains", "Financial Costs/SOLCA Contribution", 10),
    ("IVA SERVICIO DIGITAL", "contains", "Financial Costs/Taxes on Digital Services", 10),
    ("SEG. DESGRAVAMEN", "contains", "Financial Costs/Bank Fees", 10),
    # Before the general AMAZON rule (priority 30): AWS is a developer tool, not shopping.
    ("AMAZON WEB SERVICES", "contains", "Subscriptions & Software/AI & Dev Tools", 10),
]
