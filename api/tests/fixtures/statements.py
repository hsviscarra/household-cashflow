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


SAMPLES = {
    "bofa.pdf": bofa,
    "capitalone.pdf": capitalone,
    "pichincha.pdf": pichincha,
    "produbanco.pdf": produbanco,
    "diners.pdf": diners,
    "unknown.pdf": unknown,
}


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, make in SAMPLES.items():
        (out / f"sample-{name}").write_bytes(make())
