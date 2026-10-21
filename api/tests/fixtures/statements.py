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


def diners(name: str = "PRUEBA HERNAN TITULAR", card: str = "1234") -> bytes:
    return pdf(
        [
            "Estado de cuenta",
            "Período actual:",
            "04 JUN 2026 AL 03 JUL 2026",
            f"{name} 0036-xxxx-xxxx-{card} * PRINCIPAL DC SPHAERA MILES",
            "www.dinersclub.com.ec",
        ]
    )


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


# ---------------- a full Bank of America combined statement (golden test, F5) ----------------
BOFA_CHK_DEPOSITS = [
    ("09/21/26", 'Transfer Kenility LLC Via WISE from Kenility LLC ; "August"', "4,000.00")
]
BOFA_CHK_WITHDRAWALS = [
    (
        "08/28/26",
        "Agent Assisted Automatic transfer to SAV 1862 Confirmation# 1111111111",
        "-25.00",
    ),
    ("08/31/26", "CAPITAL ONE DES:MOBILE PMT ID:TEST0001 INDN:Test Holder CO", "-1,500.00"),
    ("09/08/26", "PAYPAL DES:PURCHASE ID:FABLETICSLL INDN:Test Holder CO", "-30.00"),
    ("09/11/26", "Zelle payment to TEST PERSON Conf# abc123", "-200.00"),
]
BOFA_SAV_DEPOSITS = [
    (
        "08/28/26",
        "Agent Assisted Automatic transfer from CHK 8872 Confirmation# 1111111111",
        "25.00",
    )
]
BOFA_SAV_FEES = [("08/24/26", "Monthly Maintenance Fee", "-5.00")]


def bofa_full(
    *,
    chk_begin: str = "2,000.00",
    sav_begin: str = "100.00",
    period: tuple[str, str] = ("August 22, 2026", "September 22, 2026"),
    printed_withdrawals_delta: str = "0.00",
) -> bytes:
    from decimal import Decimal

    def d(x: str) -> Decimal:
        return Decimal(x.replace(",", ""))

    def f(x: Decimal) -> str:
        return f"{x:,.2f}"

    dep = sum((d(a) for *_, a in BOFA_CHK_DEPOSITS), Decimal(0))
    wd = sum((d(a) for *_, a in BOFA_CHK_WITHDRAWALS), Decimal(0))
    chk_end = d(chk_begin) + dep + wd
    sdep = sum((d(a) for *_, a in BOFA_SAV_DEPOSITS), Decimal(0))
    sfee = sum((d(a) for *_, a in BOFA_SAV_FEES), Decimal(0))
    sav_end = d(sav_begin) + sdep + sfee
    printed_wd = wd + Decimal(printed_withdrawals_delta)
    page1 = [
        "Customer service information  bankofamerica.com",
        "Your combined statement",
        f"for {period[0]} to {period[1]}",
        "Your deposit accounts Account/plan number Ending balance Details on",
        f"Adv Plus Banking 0000 1111 8872 ${f(chk_end)} Page 2",
        f"Regular Savings 0000 2222 1862 ${f(sav_end)} Page 4",
    ]
    page2 = [
        "Account number: 0000 1111 8872",
        "Your Adv Plus Banking",
        "Account summary",
        f"Beginning balance on {period[0]} ${chk_begin}",
        f"Deposits and other additions {f(dep)}",
        f"Withdrawals and other subtractions {f(printed_wd)}",
        "Checks -0.00",
        "Service fees -0.00",
        f"Ending balance on {period[1]} ${f(chk_end)}",
        "Deposits and other additions",
        "Date Description Amount",
        *[f"{a} {b} {c}" for a, b, c in BOFA_CHK_DEPOSITS],
        f"Total deposits and other additions ${f(dep)}",
        "Withdrawals and other subtractions",
        "Date Description Amount",
        *[f"{a} {b} {c}" for a, b, c in BOFA_CHK_WITHDRAWALS[:2]],
        "ID:9999999 WEB",
        "continued on the next page",
        "Pause and verify to help prevent scams.",
        "Page 2 of 5",
    ]
    page3 = [
        "TEST HOLDER ! Account # 0000 1111 8872 ! August 22, 2026 to September 22, 2026",
        "Withdrawals and other subtractions - continued",
        "Date Description Amount",
        *[f"{a} {b} {c}" for a, b, c in BOFA_CHK_WITHDRAWALS[2:]],
        "WEB",
        f"Total withdrawals and other subtractions -${f(-wd)}",
        "Page 3 of 5",
    ]
    page4 = [
        "Account number: 0000 2222 1862",
        "Your Regular Savings",
        "Account summary",
        f"Beginning balance on {period[0]} ${sav_begin}",
        f"Deposits and other additions {f(sdep)}",
        "Withdrawals and other subtractions -0.00",
        f"Service fees {f(sfee)}",
        f"Ending balance on {period[1]} ${f(sav_end)}",
        "Deposits and other additions",
        "Date Description Amount",
        *[f"{a} {b} {c}" for a, b, c in BOFA_SAV_DEPOSITS],
        f"Total deposits and other additions ${f(sdep)}",
        "Service fees",
        "Date Transaction description Amount",
        *[f"{a} {b} {c}" for a, b, c in BOFA_SAV_FEES],
        f"Total service fees -${f(-sfee)}",
        "Note your Ending Balance already reflects the subtraction of Service Fees.",
        "Page 4 of 5",
    ]
    return pdf(page1, page2, page3, page4, ["This page intentionally left blank"])


# ---------------- a full Banco Pichincha Mastercard statement (golden test, F6) ----------------
PICH_ACCOUNT_LINES = [
    '19/06 682215 SU PAGO "MUCHAS GRACIAS" 300,00-',
    "12/07 5034 INTERESES SALDO A FAVOR N/C 0,03-",
    "12/07 INT. FINANCIAMIENTO N/D 0,50",
    "03/07 978746 ND PRECANCELACION DIF. C. N/D 100,00",
    "12/07 CONT_FIN_SOLCA_C.ROT** N/D 0,02",
]
PICH_CARD_6331 = [
    "16/06 3541282 UBER *ONE MEMBERSHIP U V CONSUMO NLD 3,99",
    "16/06 3541282 RET IVA SERV DIGITAL 100% N/D 0,60",
    "17/06 3590964 GOOGLE *YouTubeA M CONSUMO USA 7,99",
    "20/06 3703738 TIENDA DE PRUEBA DIFERIDO CONSUMO 2/6 50,00 200,00",
]
PICH_CARD_2829 = ["06/07 982931 CONECEL VARIOS UIO CONSUMO 1.024,14"]


def pichincha_full(*, previous: str = "400,00", subtotal_delta: str = "0") -> bytes:
    from decimal import Decimal

    from app.ingestion.parsers.pichincha import LINE, amount

    def val(line: str) -> Decimal:
        m = LINE.match(line)
        assert m, line
        return amount(m.group("amt"))

    acct = [val(x) for x in PICH_ACCOUNT_LINES]
    c6331 = sum((val(x) for x in PICH_CARD_6331), Decimal(0))
    c2829 = sum((val(x) for x in PICH_CARD_2829), Decimal(0))
    credits = -sum((v for v in acct if v < 0), Decimal(0))
    debits = sum((v for v in acct if v > 0), Decimal(0)) + c6331 + c2829
    prev = amount(previous)
    due = prev - credits + debits
    purchases = Decimal("3.99") + Decimal("7.99") + Decimal("50.00") + Decimal("1024.14")

    def us(x: Decimal) -> str:
        return f"{x:,.2f}"

    def ec(x: Decimal) -> str:
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    page1 = [
        "TARJETA MASTERCARD",
        "BANCO PICHINCHA C.A.",
        "inconformidad: serviciostarjetas@pichincha.com",
        "TITULAR DE PRUEBA",
        "546600XXXXXX2829 FECHA DE EMISIÓN: 12 JUL 2026",
    ]
    page2 = [
        "TARJETA MASTERCARD",
        "FECHA DE EMISIÓN FECHA MÁXIMA DE PAGO SIN RECARGOS PERÍODO DESDE PERÍODO HASTA",
        "12 JUL 2026 31 JUL 2026 13/06/2026 12/07/2026",
        "RESUMEN DE SALDO ANTERIOR PAGOS/CRÉDITOS CONSUMOS/DÉBITO TOTAL A PAGAR",
        f"MOVIMIENTO {us(prev)} {us(credits)}- {us(debits)} {us(due)}",
    ]
    page3 = [
        "TARJETA MASTERCARD",
        "DETALLE DE MOVIMIENTOS",
        "Fecha Referencia Descripción Operación Valores Diferido",
        f"SALDO ANTERIOR {ec(prev)}",
        PICH_ACCOUNT_LINES[0],
        "SUBTOTAL PAGOS 300,00",
        *PICH_ACCOUNT_LINES[1:],
        "PRUEBA HERNAN TITULAR 5466-xxxx-xxxx-6331 * PRINCIPAL REEMPLAZO MSC BLACK MILES BP",
        *PICH_CARD_6331,
        f"SUBTOTAL : {ec(c6331 + Decimal(subtotal_delta))}",
        "PRUEBA HERNAN TITULAR 5466-xxxx-xxxx-2829 * PRINCIPAL MSC BLACK MILES BP",
        *PICH_CARD_2829,
        f"SUBTOTAL : {ec(c2829)}",
        f"TOTAL CONSUMOS MES {us(purchases)}",
        f"TOTAL A PAGAR USD {us(due)}",
        "PAGO MINIMO 30.00",
        "* Contribución al financiamiento de la atención integral del cáncer, crédito diferido.",
    ]
    return pdf(page1, page2, page3)


PRODU_LINES = [
    ("Jul 1", "100000000001", "TRANSFERENCIA INTERBANCARIA B.L.", "-150.00"),
    ("Jul 1", "100000000002", "# TARIFA POR TRANSF.INTERBANCARIA B.L", "-0.41"),
    ("Jul 3", "100000000003", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+600.00"),
    ("Jul 8", "100000000004", "PAGO IESS BANCA EN LINEA", "-100.00"),
    ("Jul 8", "100000000005", "# TARIFA IESS BANCA EN LINEA", "-0.35"),
    ("Jul 9", "100000000006", "PAGO IESS BANCA EN LINEA", "-500.00"),
    ("Jul 15", "400000XXXXXX0001", "DEBITO VISA", "-25.50"),
    ("Jul 20", "20000000-0001", "PAGO TARJETA CREDITO PAGO DIRECTO B", "-1,080.00"),
    ("Jul 20", "100000000007", "# TARIFA PAGO TARJETA OTRO EMISOR BL", "-0.35"),
    ("Jul 31", "20260731", "CAPITALIZACION DE INTERESES EN CUEN", "+0.01"),
]


def produbanco_full(
    *,
    account: str = "99999993721",
    opening: str = "1500.00",
    period: str = "Del 01 Jul 2026 Al 31 Jul 2026",
    lines: list[tuple[str, str, str, str]] | None = None,
    balance_delta: str = "0",
) -> bytes:
    """Synthetic Produbanco savings statement; balance_delta misprints one running balance."""
    from decimal import Decimal

    rows = PRODU_LINES if lines is None else lines
    bal = Decimal(opening)
    detail = []
    for i, (day, ref, desc, amt) in enumerate(rows):
        bal += Decimal(amt.replace(",", ""))
        shown = bal + (Decimal(balance_delta) if i == 3 else 0)
        detail.append(f"Quito {day} {ref} {desc} {amt} {shown:,.2f} {shown:,.2f}")
    return pdf(
        [
            "Cuenta de ahorros Estado Digital de Cuenta",
            "TITULAR DE PRUEBA",
            f"CUENTA: {account} / TELF.:",
            f"Fecha Corte: {period}",
            "Resumen de transacciones",
            f"Saldo inicial contable: {Decimal(opening):,.2f}",
            f"Saldo final contable: {bal:,.2f}",
            "(#) TOTAL BASE IMPONIBLE IVA 15% 0.96",
            "(#) TOTAL IVA 15% 0.15",
            "Detalle de Transacciones",
            "Ciudad Fecha Número Descripción Valor Contable Disponible",
            *detail,
            "produbanco.com",
        ]
    )


DINERS_HERNAN = [
    "10/11 1 COLEGIO DE PRUEBA CUMBAYA (8/12) 300,00 1.200,00",
    "26/06 10001 TIENDA DE PRUEBA 17,25",
    "10/06 10002 PTP - SEGURO DE PRUEBA 9,50",
    "14/06 10003 LAVANDERIA DE PRUEBA 1.038,59",
    "02/07 10004 DN AMAZON WEB SERVICES 0,45",
    "02/07 10004 RET IVA SERV DIGITAL 100% 0,07",
]
DINERS_ADDITIONAL = ["20/06 10005 SUPERMAXI CUMBAYA 45,50"]
DINERS_DEBITS = [
    "03/07 GASTO GESTION COBRANZAS N/D T15 9,57",
    "03/07 INTERESES DE MORA N/D 1,24",
    "03/07 INT. FINANCIAMIENTO N/D 0,60",
    "03/07 CONT_FIN_SOLCA_C.ROT** N/D 0,02",
]


def diners_full(*, previous: str = "650,00", subtotal_delta: str = "0") -> bytes:
    """Synthetic Diners statement: a main card, an additional card, deferred purchase, charges."""
    from decimal import Decimal

    from app.ingestion.parsers.pichincha import amount

    def total(lines: list[str]) -> Decimal:  # the last amount on each line
        return sum((amount(x.split()[-1]) for x in lines), Decimal(0))

    def ec(x: Decimal) -> str:
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    hernan = Decimal("300.00") + total(DINERS_HERNAN[1:])  # the installment, not its balance
    extra = total(DINERS_ADDITIONAL)
    debits = total(DINERS_DEBITS)
    prev = amount(previous)
    purchases = hernan + extra
    due = purchases + debits  # the previous balance is paid in full
    main = "PRUEBA HERNAN TITULAR"
    page1 = [
        "Estado de cuenta",
        f"{main} FECHA DE CORTE:",
        "Período actual:",
        "QUITO 04 JUN 2026 AL 03 JUL 2026",
        f"SALDO ANTERIOR: {ec(prev)}",
        f"PAGOS/CRÉDITOS: {ec(prev)}- SALUD: 9,50 (1%)",
        f"CONSUMOS: {ec(purchases)} HOGAR: 10,00 (1%)",
        f"DÉBITOS: {ec(debits)}",
        f"Total a pagar: {ec(due)} OTROS: 0,07 (0%)",
        "www.dinersclub.com.ec",
    ]
    page2 = [
        "Detalle de movimientos",
        "Consumo período actual",
        "FECHA Nº VALE ESTABLECIMIENTO CUOTA VALOR IVA SALDO DIF.",
        f"{main} 0036-xxxx-xxxx-1234 * PRINCIPAL DC SPHAERA MILES PAGO MIN",
        *DINERS_HERNAN,
        f"SUBTOTAL DE CONSUMOS: {ec(hernan + Decimal(subtotal_delta))}",
        "PRUEBA LAUREN ADICIONAL 0036-xxxx-xxxx-5678 * ADICIONAL DC SPHAERA MILES",
        *DINERS_ADDITIONAL,
        f"SUBTOTAL DE CONSUMOS: {ec(extra)}",
        f"TOTAL DE CONSUMOS: {ec(purchases)} 1.200,00",
        "Detalle débitos y créditos",
        "FECHA Nº VALE DESCRIPCIÓN VALOR",
        f"SALDO ANTERIOR {ec(prev)}",
        "DETALLE DE DÉBITOS",
        *DINERS_DEBITS,
        f"TOTAL DÉBITOS: {ec(debits)}",
        "DETALLE DE PAGOS Y CRÉDITOS",
        f'16/06 11111 SU PAGO "MUCHAS GRACIAS" {ec(prev)}-',
        "SIGUE A LA SIGUIENTE PÁGINA",
    ]
    page3 = [
        "Detalle de movimientos",
        "Detalle débitos y créditos",
        "FECHA Nº VALE DESCRIPCIÓN VALOR",
        f"TOTAL PAGOS Y CRÉDITOS: {ec(prev)}-",
        f"TOTAL A PAGAR: {ec(due)}",
        "MÍNIMO A PAGAR: 320,00",
        "Resumen consumos por cliente",
        f"{main} {ec(hernan)}",
        f"PRUEBA LAUREN ADICIONAL {ec(extra)}",
        f"TOTAL CONSUMO POR CLIENTE: {ec(purchases)}",
        "Consumo en el exterior",
        "FECHA ESTABLECIMIENTO M/E* VALORUSD IVA** IVA*** TARIFA TOTAL",
        f"{main} 0036-xxxx-xxxx-1234 * PRINCIPAL DC SPHAERA MILES",
        "02/07 DN AMAZON WEB SERVICES 0,00 0,45 0,07 0,00 0,00 0,52",
    ]
    return pdf(page1, page2, page3)


PACIFICARD_LINES = [
    ("AGO/28", "100001", "SEG. DESGRAVAMEN SALDO QUITO", "CONS", "3.65", None, "+"),
    ("SEP/08", "100002", "SU PAGO PAGO DIRECTO BDP GUAYAQUI", "PAGO", "100.00", None, "-"),
    ("SEP/24", "200001", "CARGOS CAPITAL ANTERIOR", "INT", "4.20", None, "+"),
    ("SEP/24", "100003", "CONTRIB. FINANC.SOLCA ROT. (0.50%)", "CONS", "0.19", None, "+"),
    ("SEP/10", "100004", "SUPERMAXI CUMBAYA QUITO", "CONS", "45.50", None, "+"),
]
PACIFICARD_ADDITIONAL = [
    ("SEP/07", "100005", "SERV. RENOVACION TARJ/CHIP", "CONS", "5.03", None, "+"),
]
PACIFICARD_ABROAD = [
    ("SEP/05", "100006", "SERVICIO DIGITAL DE PRUEBA SEATTLE", "CONS", "57.39", "57.39", "+"),
    ("SEP/05", "100006", "N/D COMISION CONSUMO EXT I SEATTLE", "N/D", "1.96", None, "+"),
    ("SEP/05", "100006", "N/D IVA SERVICIO DIGITAL SEATTLE", "N/D", "8.61", None, "+"),
]


def pacificard_full(*, opening: str = "500.00") -> bytes:
    """Synthetic Pacificard statement as the bank delivers it: a PDF holding one screenshot of the
    web statement (statement, then a second page banner and fine print), with a grey watermark."""
    from decimal import Decimal

    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader

    rows = PACIFICARD_LINES + PACIFICARD_ADDITIONAL + PACIFICARD_ABROAD
    signed = {"+": Decimal(1), "-": Decimal(-1)}
    by_op: dict[str, Decimal] = {
        "purchases": Decimal(0),
        "payments": Decimal(0),
        "charges": Decimal(0),
    }
    for _d, _r, _desc, op, amt, _fx, sign in rows:
        group = {"PAGO": "payments", "INT": "charges"}.get(op, "purchases")
        by_op[group] += signed[sign] * Decimal(amt)
    prev = Decimal(opening)
    purchases, paid, charges = by_op["purchases"], -by_op["payments"], by_op["charges"]
    due = prev + purchases - paid + charges

    def row(d: str, ref: str, desc: str, op: str, amt: str, fx: str | None, sign: str) -> str:
        return f"{d} {ref} {desc:<38} {op:<5} {amt:>8} {fx or '':>8} {sign}"

    text = [
        "Estado de cuenta                                   PacifiCard",
        "Cliente PRUEBA                       BANCO DEL PACIFICO S.A.",
        "PRUEBA HERNAN TITULAR                webadminpac@pacifico.fin.ec",
        "                                     MASTERCARD: 5451-00XX-XXXX-X123 Black",
        "Periodo de corte desde: 25/AGO/2026 hasta 24/SEP/2026",
        "Fecha de corte: 24/SEP/2026",
        f"{prev:.2f} {purchases:.2f} {paid:.2f} {charges:.2f} {due:.2f}",
        f"Deuda Total {due:.2f} 100% {due:.2f}",
        "",
        "DETALLE DE MOVIMIENTOS DEL PERIODO",
        "FECHA REFER. DESCRIPCION OPERACION US$ EXTRANJERA",
        f"****** SALDO ANTERIOR {prev:.2f}",
        "*** DETALLE DE CONSUMOS LOCALES",
        "0000000001 PRUEBA HERNAN TITULAR",
        *[row(*r) for r in PACIFICARD_LINES],
        "0000000002 PRUEBA LAUREN ADICIONAL",
        *[row(*r) for r in PACIFICARD_ADDITIONAL],
        "*** DETALLE DE CONSUMOS EN EL EXTERIOR",
        "0000000001 PRUEBA HERNAN TITULAR",
        *[row(*r) for r in PACIFICARD_ABROAD],
        f"TOTAL PAGO DE CONTADO {due:.2f}",
        f"SALDO ACTUAL ROTATIVO {due:.2f}",
        "SALDO ACTUAL DIFERIDO 0.00",
        f"SUBTOTAL CONSUMOS PERIODO {purchases:.2f}",
        f"SUBTOTAL PAGOS/CREDITOS {paid:.2f}",
        "INTERES FINANCIAMIENTO 0.00",
        "INTERES POR MORA 0.00",
        "ORIGINAL - CLIENTE",
    ]
    fine_print = ["CONCEPTOS BASICOS", *["Texto informativo de prueba 1.00 2.00 3.00"] * 12]
    width, step = 980, 20
    height = 60 + step * (len(text) + len(fine_print)) + 120
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=14)
    draw.rectangle((40, 10, width - 40, 40), fill=(28, 43, 74))  # page 1 banner
    y = 60
    for line in text:
        draw.text((50, y), line, fill="black", font=font)
        y += step
    draw.rectangle((40, y + 30, width - 40, y + 60), fill=(28, 43, 74))  # "Pag. 2" banner
    y += 90
    for line in fine_print:
        draw.text((50, y), line, fill="black", font=font)
        y += step
    mark = ImageFont.load_default(size=160)
    draw.text((180, 250), "COPIA", fill=(191, 191, 191), font=mark)  # watermark under the text
    for i, line in enumerate(
        text[9:16]
    ):  # the watermark covers part of the detail, like the real one
        draw.text((50, 60 + step * (9 + i)), line, fill="black", font=font)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter, invariant=1)
    picture = ImageReader(BytesIO(buf.getvalue()))
    for _ in range(2):  # both pages show the same picture, as the bank's PDF does
        c.drawImage(picture, 20, 20, width=572, height=752, preserveAspectRatio=True)
        c.showPage()
    c.save()
    return out.getvalue()


def scanned(data: bytes, dpi: int = 200) -> bytes:
    """The same statement as a scan: every page a grey JPEG picture, no text layer."""
    import pdfplumber
    from reportlab.lib.utils import ImageReader

    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter, invariant=1)
    with pdfplumber.open(BytesIO(data)) as doc:
        for page in doc.pages:
            picture = page.to_image(resolution=dpi).original.convert("L")
            buf = BytesIO()
            picture.save(buf, format="JPEG", quality=85)
            c.drawImage(ImageReader(BytesIO(buf.getvalue())), 0, 0, width=612, height=792)
            c.showPage()
    c.save()
    return out.getvalue()


SAMPLES = {
    "bofa.pdf": bofa,
    "capitalone.pdf": capitalone,
    "pichincha.pdf": pichincha,
    "produbanco.pdf": produbanco,
    "diners.pdf": diners,
    "unknown.pdf": unknown,
    "capitalone-full.pdf": capitalone_full,
    "bofa-full.pdf": bofa_full,
    "pichincha-full.pdf": pichincha_full,
    "produbanco-full.pdf": produbanco_full,
    "diners-full.pdf": diners_full,
    "pacificard-full.pdf": pacificard_full,
}


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, make in SAMPLES.items():
        (out / f"sample-{name}").write_bytes(make())
