"""Seed v1 for the reference tables, loaded by migration 0003.

Frozen snapshot: later changes happen in the app (Settings page) or in a new seed module and
migration, never by editing this file. Accounts carry the last four digits only.
"""

from typing import TypedDict


class AccountSeed(TypedDict):
    name: str
    institution: str
    kind: str
    owner: str
    country: str
    last4: str | None


ACCOUNTS: list[AccountSeed] = [
    {
        "name": "BofA Adv Plus Banking",
        "institution": "Bank of America",
        "kind": "checking",
        "owner": "Joint",
        "country": "US",
        "last4": "8872",
    },
    {
        "name": "BofA Regular Savings",
        "institution": "Bank of America",
        "kind": "savings",
        "owner": "Joint",
        "country": "US",
        "last4": "1862",
    },
    {
        "name": "Capital One Venture",
        "institution": "Capital One",
        "kind": "credit_card",
        "owner": "Joint",
        "country": "US",
        "last4": "4003",
    },
    {
        "name": "Pichincha Mastercard Black",
        "institution": "Banco Pichincha",
        "kind": "credit_card",
        "owner": "Hernan",
        "country": "EC",
        "last4": "2829",
    },
    {
        "name": "Produbanco Ahorros Hernan",
        "institution": "Produbanco",
        "kind": "savings",
        "owner": "Hernan",
        "country": "EC",
        "last4": "3721",
    },
    {
        "name": "Produbanco Lauren",
        "institution": "Produbanco",
        "kind": "savings",
        "owner": "Lauren",
        "country": "EC",
        "last4": None,
    },
    {
        "name": "Diners Club Hernan",
        "institution": "Diners Club",
        "kind": "credit_card",
        "owner": "Hernan",
        "country": "EC",
        "last4": None,
    },
    {
        "name": "Diners Club Lauren",
        "institution": "Diners Club",
        "kind": "credit_card",
        "owner": "Lauren",
        "country": "EC",
        "last4": None,
    },
]


class GroupSeed(TypedDict):
    name: str
    kind: str
    color: str | None
    fixed: bool
    children: list[tuple[str, bool]]  # (name, is_fixed)


# Category tree from the project instructions; colors follow docs/design-system.md.
CATEGORIES: list[GroupSeed] = [
    # Income
    {
        "name": "Salary",
        "kind": "income",
        "color": "#4E9A2A",
        "fixed": False,
        "children": [("Hernan", False), ("Lauren", False)],
    },
    {"name": "Office Rent", "kind": "income", "color": "#00897B", "fixed": True, "children": []},
    {
        "name": "Insurance Reimbursement",
        "kind": "income",
        "color": "#3AA7D9",
        "fixed": False,
        "children": [],
    },
    {
        "name": "Interest Earned",
        "kind": "income",
        "color": "#7B4BD6",
        "fixed": False,
        "children": [],
    },
    {"name": "Other Income", "kind": "income", "color": "#6B6788", "fixed": False, "children": []},
    # Expenses
    {
        "name": "Housing",
        "kind": "expense",
        "color": "#6B6788",
        "fixed": False,
        "children": [
            ("Mortgage BIESS", True),
            ("Condo Fee", True),
            ("Office Alícuota", True),
            ("Home Maintenance", False),
        ],
    },
    {
        "name": "Utilities",
        "kind": "expense",
        "color": "#8D6E63",
        "fixed": False,
        "children": [("Water", False), ("Electricity", False), ("Phone/Internet", True)],
    },
    {
        "name": "Household Staff",
        "kind": "expense",
        "color": "#7B4BD6",
        "fixed": False,
        "children": [("Empleada Salary", True), ("Empleada IESS", True)],
    },
    {
        "name": "Childcare",
        "kind": "expense",
        "color": "#E57BA9",
        "fixed": False,
        "children": [("Daycare", True), ("Daycare Lunch", False), ("Baby & Kids Stores", False)],
    },
    {
        "name": "Health",
        "kind": "expense",
        "color": "#00897B",
        "fixed": False,
        "children": [
            ("Insurance", True),
            ("Doctors", False),
            ("Labs & Imaging", False),
            ("Pharmacy", False),
        ],
    },
    {
        "name": "Groceries",
        "kind": "expense",
        "color": "#4E9A2A",
        "fixed": False,
        "children": [("Supermarket", False), ("Grocery Delivery", False)],
    },
    {
        "name": "Dining",
        "kind": "expense",
        "color": "#E2583E",
        "fixed": False,
        "children": [("Food Delivery", False), ("Restaurants & Cafés", False)],
    },
    {
        "name": "Transport",
        "kind": "expense",
        "color": "#3AA7D9",
        "fixed": False,
        "children": [("Rideshare", False), ("Fuel", False), ("Parking", False), ("Vehicle", False)],
    },
    {
        "name": "Subscriptions & Software",
        "kind": "expense",
        "color": "#2F5BEA",
        "fixed": False,
        "children": [
            ("AI & Dev Tools", True),
            ("Media", True),
            ("Apps", False),
            ("Memberships", True),
            ("Professional", False),
        ],
    },
    {
        "name": "Shopping",
        "kind": "expense",
        "color": "#C2185B",
        "fixed": False,
        "children": [("Amazon", False), ("Clothing", False), ("Other Retail", False)],
    },
    {"name": "Travel", "kind": "expense", "color": "#E8A000", "fixed": False, "children": []},
    {"name": "Donations", "kind": "expense", "color": "#9C8D2B", "fixed": True, "children": []},
    {
        "name": "Financial Costs",
        "kind": "expense",
        "color": "#A3301B",
        "fixed": False,
        "children": [
            ("Credit Card Interest", False),
            ("Bank Fees", False),
            ("Taxes on Digital Services", False),
            ("SOLCA Contribution", False),
        ],
    },
    # Savings and debt, shown apart from spending
    {
        "name": "Savings & Debt",
        "kind": "savings",
        "color": "#1E3FB0",
        "fixed": False,
        "children": [
            ("Investing", True),
            ("Transfers to Savings", False),
            ("Extra Debt Payoff", False),
        ],
    },
    # Movements between own accounts, excluded from income and spending
    {
        "name": "Transfers",
        "kind": "transfer",
        "color": None,
        "fixed": False,
        "children": [("Card Payment", False), ("Between Own Accounts", False)],
    },
]


# (pattern, match_type, "Group/Subcategory", priority). Lower priority runs first.
MERCHANT_RULES: list[tuple[str, str, str, int]] = [
    ("UBER *ONE MEMBERSHIP", "contains", "Subscriptions & Software/Memberships", 10),
    ("UBER EATS", "contains", "Dining/Food Delivery", 20),
    ("UBER RIDES", "contains", "Transport/Rideshare", 20),
    ("SUPERMAXI", "contains", "Groceries/Supermarket", 20),
    ("MEGAMAXI", "contains", "Groceries/Supermarket", 20),
    ("TIPTI", "contains", "Groceries/Grocery Delivery", 20),
    ("RAPPI", "contains", "Groceries/Grocery Delivery", 30),
    ("FYBECA", "contains", "Health/Pharmacy", 20),
    ("ZURITA Y ZURITA", "contains", "Health/Labs & Imaging", 20),
    ("AXXISCAN", "contains", "Health/Labs & Imaging", 20),
    ("BEBEMUNDO", "contains", "Childcare/Baby & Kids Stores", 20),
    ("JUGUETON", "contains", "Childcare/Baby & Kids Stores", 20),
    ("ANTHROPIC", "contains", "Subscriptions & Software/AI & Dev Tools", 20),
    ("GITHUB", "contains", "Subscriptions & Software/AI & Dev Tools", 20),
    ("YOUTUBE", "contains", "Subscriptions & Software/Media", 20),
    ("GOOGLE ONE", "contains", "Subscriptions & Software/Media", 20),
    ("KINDLE SVCS", "contains", "Subscriptions & Software/Media", 20),
    ("LINKEDIN", "contains", "Subscriptions & Software/Professional", 20),
    ("FLEXJOBS", "contains", "Subscriptions & Software/Professional", 20),
    ("BETTERME", "contains", "Subscriptions & Software/Apps", 20),
    ("GOOGLE *", "starts_with", "Subscriptions & Software/Apps", 90),
    ("AMAZON", "contains", "Shopping/Amazon", 30),
    ("FABLETICS", "contains", "Shopping/Clothing", 20),
    ("HEADCOVERS", "contains", "Shopping/Other Retail", 20),
    ("ESTACION DE SERVICIO", "contains", "Transport/Fuel", 20),
    ("ESTACIONAMIENTOS", "contains", "Transport/Parking", 20),
    ("PARKING", "contains", "Transport/Parking", 30),
    ("CONECEL", "contains", "Utilities/Phone/Internet", 20),
    ("CREPES & WAFFLES", "contains", "Dining/Restaurants & Cafés", 20),
    ("PF CHANGS", "contains", "Dining/Restaurants & Cafés", 20),
    ("CYRANO", "contains", "Dining/Restaurants & Cafés", 20),
    ("CAFFE Y NATA", "contains", "Dining/Restaurants & Cafés", 20),
    ("LA BRICIOLA", "contains", "Dining/Restaurants & Cafés", 20),
    ("RAYMI COFFEE", "contains", "Dining/Restaurants & Cafés", 20),
    ("REPUBLICA DEL CACAO", "contains", "Dining/Restaurants & Cafés", 20),
    ("BOKER TOV", "contains", "Dining/Restaurants & Cafés", 20),
    ("MEGAVICHE", "contains", "Dining/Restaurants & Cafés", 20),
    ("CAPITAL ONE MOBILE PYMT", "contains", "Transfers/Card Payment", 10),
    ("CAPITAL ONE DES:MOBILE PMT", "contains", "Transfers/Card Payment", 10),
    ("SU PAGO", "starts_with", "Transfers/Card Payment", 10),
    ("AUTOMATIC TRANSFER TO SAV", "contains", "Transfers/Between Own Accounts", 10),
    ("AUTOMATIC TRANSFER FROM CHK", "contains", "Transfers/Between Own Accounts", 10),
    ("TRANSFER KENILITY", "contains", "Salary/Hernan", 10),
    ("INTEREST CHARGE", "contains", "Financial Costs/Credit Card Interest", 10),
    ("INT. FINANCIAMIENTO", "contains", "Financial Costs/Credit Card Interest", 10),
    ("RET IVA SERV DIGITAL", "contains", "Financial Costs/Taxes on Digital Services", 10),
    ("CONT_FIN_SOLCA", "contains", "Financial Costs/SOLCA Contribution", 10),
    ("MONTHLY MAINTENANCE FEE", "contains", "Financial Costs/Bank Fees", 10),
    ("TARIFA", "starts_with", "Financial Costs/Bank Fees", 10),
    ("PRECANCELACION DIF", "contains", "Savings & Debt/Extra Debt Payoff", 10),
]
