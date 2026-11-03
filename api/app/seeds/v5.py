"""Seed v5 (F23): a description for every seeded category, so the picker can say what goes where
(and Claude's suggestions read the same text). Drafted from the merchants the seeded rules
already map; Hernan edits them in Settings. Frozen like the earlier seeds: a migration fills only
categories whose description is still empty, matched by "Group" or "Group/Sub".
"""

DESCRIPTIONS: dict[str, str] = {
    # ---------- income ----------
    "Salary": "Pay for Hernan's and Lauren's work. Pick the person who earned it.",
    "Salary/Hernan": "Hernan's pay, e.g. the Kenility transfer. Not reimbursements (Other Income).",
    "Salary/Lauren": "Lauren's pay from her job.",
    "Office Rent": "Rent the tenants of the office pay you each month.",
    "Insurance Reimbursement": (
        "Money an insurer pays back for medical bills (e.g. BMI refunds). The bills themselves "
        "go to Health."
    ),
    "Interest Earned": (
        "Interest paid by a bank or savings account, including interest on a credit balance."
    ),
    "Other Income": (
        "Money in that isn't pay, rent, a refund of a purchase or a transfer between your own "
        "accounts: gifts, sales of things, one-off payments."
    ),
    # ---------- housing and bills ----------
    "Housing": "The house and the office as places: loan, condo fees, repairs.",
    "Housing/Mortgage BIESS": (
        "The BIESS house loan installment (the larger PAGO IESS). The empleada's IESS is under "
        "Household Staff."
    ),
    "Housing/Condo Fee": "The building's monthly alícuota for the home.",
    "Housing/Office Alícuota": "The building's monthly alícuota for the office.",
    "Housing/Home Maintenance": (
        "Repairs, plumbers, electricians, paint, hardware stores (Kywi) and things to fix the "
        "house."
    ),
    "Utilities": "Monthly service bills for the home.",
    "Utilities/Water": "EPMAPS water bill.",
    "Utilities/Electricity": "Empresa Eléctrica Quito bill.",
    "Utilities/Phone/Internet": (
        "Mobile plans and home internet: Claro (CONECEL), Movistar, Netlife."
    ),
    "Household Staff": "The empleada's pay and her social security.",
    "Household Staff/Empleada Salary": "The empleada's monthly salary, décimos and bonuses.",
    "Household Staff/Empleada IESS": (
        "The empleada's IESS contribution (the smaller PAGO IESS; the BIESS loan is under Housing)."
    ),
    # ---------- family ----------
    "Childcare": "Daycare and things for the kids.",
    "Childcare/Daycare": "The daycare's monthly fee.",
    "Childcare/Daycare Lunch": "Lunch paid to the daycare.",
    "Childcare/Baby & Kids Stores": (
        "Clothes, toys and baby supplies from kids' stores: Bebemundo, Juguetón. Diapers bought"
        " at the supermarket stay in Groceries."
    ),
    "Health": "Health insurance and medical care for the family.",
    "Health/Insurance": "The family's health plan, e.g. BMI Igualas Médicas installments.",
    "Health/Doctors": "Doctor and dentist visits, therapists, hospital bills.",
    "Health/Labs & Imaging": "Blood tests, X-rays and scans: Zurita & Zurita, Axxiscan.",
    "Health/Pharmacy": "Medicines and pharmacy purchases: Fybeca, Pharmacys, Cruz Azul.",
    "Health/Dad's Insurance": "The health insurance you pay for your dad.",
    "Pets": "Everything for the pets.",
    "Pets/Pet Daycare": (
        "Pet daycare, walking and boarding. Food and vet visits go to the group Pets."
    ),
    # ---------- food ----------
    "Groceries": "Food and household supplies for the home.",
    "Groceries/Supermarket": (
        "Supermaxi, Megamaxi, Mi Comisariato, markets: the weekly shop in person."
    ),
    "Groceries/Grocery Delivery": "Groceries delivered: Tipti, Rappi market orders.",
    "Dining": "Food eaten out or delivered ready to eat.",
    "Dining/Food Delivery": "Ready meals delivered: Uber Eats, Rappi restaurants, PedidosYa.",
    "Dining/Restaurants & Cafés": (
        "Restaurants, cafés and bakeries in person: Crepes & Waffles, Café y Nata, Republica "
        "del Cacao."
    ),
    # ---------- getting around ----------
    "Transport": "Getting around: rides, the car and parking.",
    "Transport/Rideshare": "Uber rides, Cabify, taxis. Uber One membership is under Subscriptions.",
    "Transport/Fuel": "Gas stations (estaciones de servicio).",
    "Transport/Parking": "Parking lots and meters (estacionamientos).",
    "Transport/Vehicle": "Car maintenance, insurance, registration (matrícula), tolls and tires.",
    "Travel": "Trips away from home: flights, hotels, Airbnb, travel insurance, tours.",
    # ---------- subscriptions and shopping ----------
    "Subscriptions & Software": "Recurring digital charges, billed monthly or yearly.",
    "Subscriptions & Software/AI & Dev Tools": (
        "Anthropic, OpenAI (ChatGPT), GitHub, AWS and other tools for building software."
    ),
    "Subscriptions & Software/Media": (
        "Video, music, books and storage to consume: YouTube Premium, Google One, Kindle, "
        "Medium, Netflix, Spotify."
    ),
    "Subscriptions & Software/Apps": (
        "Phone apps billed through Google Play or the App Store (charges like 'GOOGLE *App "
        "name'): photo editors, language apps, BetterMe."
    ),
    "Subscriptions & Software/Memberships": (
        "Memberships with perks: Uber One, Amazon Prime, Costco, gyms."
    ),
    "Subscriptions & Software/Professional": (
        "Work-related services: LinkedIn, FlexJobs, Microsoft 365, certifications."
    ),
    "Shopping": "Things you buy that aren't food, health or kids' items.",
    "Shopping/Amazon": "Amazon orders. Amazon Prime and Kindle are under Subscriptions.",
    "Shopping/Clothing": "Clothes and shoes for adults: Fabletics, De Prati, Zara.",
    "Shopping/Other Retail": "Other stores: electronics, home goods, sports, gifts.",
    "Donations": "Gifts to charities, churches and causes.",
    # ---------- bank costs ----------
    "Financial Costs": "What banks and the government charge on your cards and accounts.",
    "Financial Costs/Credit Card Interest": (
        "Interest on card balances: INTEREST CHARGE, INT. FINANCIAMIENTO, CARGOS CAPITAL ANTERIOR."
    ),
    "Financial Costs/Bank Fees": (
        "Bank and card fees: maintenance, card renewal, foreign-purchase commissions, SEG. "
        "DESGRAVAMEN (the card's credit life insurance)."
    ),
    "Financial Costs/Taxes on Digital Services": (
        "The IVA Ecuadorian banks add to foreign digital purchases (RET IVA SERV DIGITAL, IVA "
        "SERVICIO DIGITAL) right after a Google, Uber or Netflix charge."
    ),
    "Financial Costs/SOLCA Contribution": "The 0.5% SOLCA cancer contribution on card balances.",
    # ---------- savings and moving money ----------
    "Savings & Debt": "Money set aside or used to pay debt down. Not spending.",
    "Savings & Debt/Investing": "Money sent to Interactive Brokers or other investments.",
    "Savings & Debt/Transfers to Savings": "Money moved into a savings account to keep.",
    "Savings & Debt/Extra Debt Payoff": (
        "Paying a loan or a deferred card purchase early (PRECANCELACION DIF), beyond the "
        "installment."
    ),
    "Savings & Debt/Loan Payments": "Regular installments of a loan other than the BIESS mortgage.",
    "Transfers": "Money moving between your own accounts and cards. Not income or spending.",
    "Transfers/Card Payment": (
        "Paying a credit card from a bank account (SU PAGO, CAPITAL ONE MOBILE PYMT). Both "
        "sides use this, so they cancel out."
    ),
    "Transfers/Between Own Accounts": (
        "Moving money between your own accounts, e.g. checking to savings."
    ),
    "Other Expenses": (
        "When you're not sure yet: park a line here and move it later. The Spending page shows "
        "what's waiting here."
    ),
}
