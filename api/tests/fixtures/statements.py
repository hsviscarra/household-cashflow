"""Synthetic statement PDFs: each bank's fingerprint layout with made-up holders and amounts.

uv run python -m tests.fixtures.statements ../web/e2e/fixtures   # writes the e2e samples
"""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def pdf(*pages: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)  # same bytes every time
    for lines in pages:
        y = 740
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


def bofa() -> bytes:
    return pdf(
        [
            "Customer service: 1.800.000.0000  bankofamerica.com",
            "Bank of America, N.A.",
            "TEST HOLDER ONE",
            "Your combined statement",
            "for August 22, 2026 to September 22, 2026",
            "Adv Plus Banking 0000 1111 8872 $1,234.56",
            "Regular Savings 0000 2222 1862 $100.00",
        ],
        ["Deposits and other additions", "09/01/26 TEST DEPOSIT 10.00"],
    )


def capitalone(last4: str = "4003") -> bytes:
    return pdf(
        [
            "Previous Balance $100.00",
            f"Venture Credit Card | Visa Signature ending in {last4}",
            "Sep 04, 2026 - Oct 03, 2026 | 30 days in Billing Cycle",
            "Pay or manage your account at capitalone.com",
            "CAPITAL ONE MOBILE PYMT - 50.00",
        ]
    )


def pichincha(card: str = "546600XXXXXX2829") -> bytes:
    return pdf(
        ["TARJETA MASTERCARD", "BANCO PICHINCHA C.A.", "TITULAR DE PRUEBA", card],
        ["PERIODO DESDE PERIODO HASTA", "13/06/2026", "12/07/2026", "SALDO ANTERIOR 10.00"],
    )


def produbanco(account: str = "99999993721") -> bytes:
    return pdf(
        [
            "Cuenta de ahorros  Estado Digital de Cuenta",
            "TITULAR DE PRUEBA",
            f"CUENTA: {account} / TELF.:",
            "Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026",
            "Saldo inicial contable: 10.00",
            "produbanco.com",
        ]
    )


def diners() -> bytes:
    return pdf(["DINERS CLUB DEL ECUADOR", "www.dinersclub.com.ec", "TARJETA XXXX XXXX 1234"])


def unknown() -> bytes:
    return pdf(["Some Other Bank", "Statement of account", "Balance 10.00"])


def encrypted() -> bytes:
    writer = PdfWriter()
    for page in PdfReader(BytesIO(capitalone())).pages:
        writer.add_page(page)
    writer.encrypt(user_password="1234", owner_password="owner")
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------- a full Capital One statement (golden test, F4) ----------------
CO_LAUREN = [
    ("Sep 2", "Sep 4", "UBER EATS SAN JOSE", "12.50"),
    ("Sep 2", "Sep 4", "UBER EATS SAN JOSE", "12.50"),  # same line twice: both are real
    ("Sep 14", "Sep 16", "DL RAPPI ECUADOR Guayaquil", "15.00"),
    ("Sep 30", "Oct 1", "ANTHROPIC* CLAUDE SUB ANTHROPIC.COM CA", "20.00"),
    ("Oct 1", "Oct 3", "NEW MERCHANT XYZ MIAMI FL", "40.00"),
]
CO_HERNAN = [
    ("Sep 4", "Sep 8", "SUPERMAXI EL JARDIN QUITO", "200.00"),
    ("Sep 12", "Sep 14", "GITHUB, INC. GITHUB.COM CA", "21.32"),
    ("Sep 19", "Sep 22", "FYBECA Ruminahui", "5.43"),
    ("Sep 20", "Sep 21", "AMAZON MKTPL*REFUND Amzn.com/bill WA", "- $30.00"),
]


def capitalone_full(
    *,
    previous: str = "1000.00",
    payment: str = "500.00",
    interest: str = "10.00",
    lauren: list[tuple[str, str, str, str]] | None = None,
    hernan: list[tuple[str, str, str, str]] | None = None,
    period: tuple[str, str] = ("Sep 04, 2026", "Oct 03, 2026"),
    printed_total_delta: str = "0.00",
    extra_lines: list[str] | None = None,
    payment_dates: str = "Sep 27 Sep 28",
) -> bytes:
    from decimal import Decimal

    lauren = CO_LAUREN if lauren is None else lauren
    hernan = CO_HERNAN if hernan is None else hernan

    def amt(a: str) -> Decimal:
        return -Decimal(a[3:]) if a.startswith("- $") else Decimal(a)

    def fmt(a: str) -> str:
        return a if a.startswith("- $") else f"${Decimal(a):,.2f}"

    lt = sum((amt(x[3]) for x in lauren), Decimal(0))
    ht = sum((amt(x[3]) for x in hernan), Decimal(0))
    total = lt + ht
    new = Decimal(previous) - Decimal(payment) + total + Decimal(interest)
    head = [
        "Venture Credit Card | Visa Signature ending in 4003",
        f"{period[0]} - {period[1]} | 30 days in Billing Cycle",
    ]
    page1 = [
        "Page 1 of 4",
        *head,
        f"Payment Information Account Summary Previous Balance ${Decimal(previous):,.2f}",
        f"Payments - ${Decimal(payment):,.2f}",
        "Other Credits $0.00",
        f"Transactions + ${total + Decimal(printed_total_delta):,.2f}",
        "Cash Advances + $0.00",
        "Fees Charged + $0.00",
        f"Interest Charged + ${Decimal(interest):,.2f}",
        f"New Balance = ${new:,.2f}",
        "Pay or manage your account at capitalone.com",
    ]
    page2 = [
        "Page 2 of 4",
        *head,
        "Transactions",
        "TEST LAUREN HOLDER #4003: Payments, Credits and Adjustments",
        "Trans Date Post Date Description Amount",
        f"{payment_dates} CAPITAL ONE MOBILE PYMT - ${Decimal(payment):,.2f}",
        "TEST LAUREN HOLDER #4003: Transactions",
        "Trans Date Post Date Description Amount",
        *[f"{a} {b} {c} {fmt(d)}" for a, b, c, d in lauren],
        f"TEST LAUREN HOLDER #4003: Total Transactions ${lt:,.2f}",
        *(extra_lines or []),
    ]
    page3 = [
        "Page 3 of 4",
        *head,
        "Transactions (Continued)",
        "TEST HERNAN HOLDER #4162: Payments, Credits and Adjustments",
        "Trans Date Post Date Description Amount",
        "TEST HERNAN HOLDER #4162: Transactions",
        "Trans Date Post Date Description Amount",
        *[f"{a} {b} {c} {fmt(d)}" for a, b, c, d in hernan],
        f"TEST HERNAN HOLDER #4162: Total Transactions ${ht:,.2f}",
        f"Total Transactions for This Period ${total:,.2f}",
        "Fees",
        "Trans Date Post Date Description Amount",
        "Total Fees for This Period $0.00",
        "Interest Charged",
        f"Interest Charge on Purchases ${Decimal(interest):,.2f}",
        "Interest Charge on Cash Advances $0.00",
        f"Total Interest for This Period ${Decimal(interest):,.2f}",
        "Totals Year-to-Date",
        "Total Fees charged $0.00",
    ]
    return pdf(page1, page2, page3, ["Page 4 of 4", *head, "Interest Charge Calculation"])


SAMPLES = {
    "bofa.pdf": bofa,
    "capitalone.pdf": capitalone,
    "pichincha.pdf": pichincha,
    "produbanco.pdf": produbanco,
    "diners.pdf": diners,
    "unknown.pdf": unknown,
    "capitalone-full.pdf": capitalone_full,
}


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, make in SAMPLES.items():
        (out / f"sample-{name}").write_bytes(make())
