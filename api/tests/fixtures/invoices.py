"""Synthetic SRI electronic invoices (F21). No real vendor numbers, people or identifications."""

from decimal import Decimal

KEY = "3010202601179999999900120721400001234561234567818"  # 49 digits, made up


def factura(
    *,
    key: str = KEY,
    issuer: str = "SUPERMERCADO DE PRUEBA S.A.",
    trade_name: str = "SUPER PRUEBA",
    day: str = "28/10/2026",
    lines: list[tuple[str, str, str, str]] | None = None,
    subtotal_delta: str = "0",
    wrapped: bool = True,
    cod: str = "01",
) -> bytes:
    """An invoice; lines are (description, quantity, unit price, IVA rate %). By default it's
    wrapped as SRI returns an authorized document (<autorizacion> with the invoice in CDATA)."""
    lines = lines or [
        ("LECHE ENTERA 1L", "2", "1.05", "0"),
        ("POLLO ENTERO KG", "1.250", "3.20", "0"),
        ("DETERGENTE POLVO 2KG", "1", "6.50", "15"),
        ("YOG TONI FRUT 1L", "1", "2.40", "0"),
    ]
    details, subtotal, tax = [], Decimal(0), Decimal(0)
    for desc, qty, price, rate in lines:
        base = (Decimal(qty) * Decimal(price)).quantize(Decimal("0.01"))
        iva = (base * Decimal(rate) / 100).quantize(Decimal("0.01"))
        subtotal += base
        tax += iva
        details.append(
            f"<detalle><codigoPrincipal>{abs(hash(desc)) % 10**8}</codigoPrincipal>"
            f"<descripcion>{desc}</descripcion><cantidad>{qty}</cantidad>"
            f"<precioUnitario>{price}</precioUnitario><descuento>0.00</descuento>"
            f"<precioTotalSinImpuesto>{base}</precioTotalSinImpuesto><impuestos><impuesto>"
            f"<codigo>2</codigo><codigoPorcentaje>{4 if rate != '0' else 0}</codigoPorcentaje>"
            f"<tarifa>{rate}</tarifa><baseImponible>{base}</baseImponible><valor>{iva}</valor>"
            f"</impuesto></impuestos></detalle>"
        )
    printed = subtotal + Decimal(subtotal_delta)
    tag = {"01": "factura", "04": "notaCredito"}[cod]
    doc = (
        f'<?xml version="1.0" encoding="UTF-8"?><{tag} id="comprobante" version="1.1.0">'
        f"<infoTributaria><ambiente>2</ambiente><tipoEmision>1</tipoEmision>"
        f"<razonSocial>{issuer}</razonSocial><nombreComercial>{trade_name}</nombreComercial>"
        f"<ruc>1799999999001</ruc><claveAcceso>{key}</claveAcceso><codDoc>{cod}</codDoc>"
        f"<estab>072</estab><ptoEmi>140</ptoEmi><secuencial>000123456</secuencial>"
        f"<dirMatriz>CALLE DE PRUEBA</dirMatriz></infoTributaria>"
        f"<infoFactura><fechaEmision>{day}</fechaEmision>"
        f"<tipoIdentificacionComprador>05</tipoIdentificacionComprador>"
        f"<razonSocialComprador>CLIENTE DE PRUEBA</razonSocialComprador>"
        f"<identificacionComprador>0000000000</identificacionComprador>"
        f"<totalSinImpuestos>{printed}</totalSinImpuestos><totalDescuento>0.00</totalDescuento>"
        f"<totalConImpuestos><totalImpuesto><codigo>2</codigo><codigoPorcentaje>4"
        f"</codigoPorcentaje><baseImponible>{subtotal}</baseImponible><valor>{tax}</valor>"
        f"</totalImpuesto></totalConImpuestos><propina>0.00</propina>"
        f"<importeTotal>{subtotal + tax}</importeTotal><moneda>DOLAR</moneda></infoFactura>"
        f"<detalles>{''.join(details)}</detalles></{tag}>"
    )
    if not wrapped:
        return doc.encode()
    return (
        '<?xml version="1.0" encoding="UTF-8"?><autorizacion><estado>AUTORIZADO</estado>'
        f"<numeroAutorizacion>{key}</numeroAutorizacion>"
        "<fechaAutorizacion>2026-10-28T18:46:43</fechaAutorizacion><ambiente>PRODUCCION</ambiente>"
        f"<comprobante><![CDATA[{doc}]]></comprobante></autorizacion>"
    ).encode()


# The default invoice: 2.10 + 4.00 + 6.50 (+0.98 IVA) + 2.40 = 15.98.
TOTAL = Decimal("15.98")
