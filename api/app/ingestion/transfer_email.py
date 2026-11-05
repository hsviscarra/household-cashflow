"""Transfer notices by email (ADR-023): Produbanco's and Pichincha's emails become transfer notes.

The statements print "TRANSFERENCIA"; the bank's email, sent the moment the transfer is made,
names the other party and carries the description typed at the bank. The Gmail script posts each
notice's subject and text; this module reads them into a `Notice`. Only what the note needs is
kept: date, amount, direction, which of the household's accounts (by its last 4 digits), the
other party's name, the description and the bank's reference. Cédulas and full account numbers
in the email are never stored.

Formats (synthetic examples in tests/fixtures/transfer_emails.py):
- Produbanco "Transferencia enviada por $X desde Produbanco": sent from Hernan's Produbanco
  account (the email doesn't print its number) to "Contacto", "Cuenta Destino".
- Produbanco "Transferencia Recibida en Produbanco": received from another bank into
  "Cuenta Beneficiario", from "Enviada por".
- Produbanco "Transferencia acreditada Produbanco": received from another Produbanco client into
  "Cuenta Destino"; the sender is in "Te confirmamos que <name> ha realizado...".
- Produbanco "Transferencia recibida desde Produbanco": the copy for a beneficiary at another bank
  ("Cuenta Destino" there), from the same sentence.
- Pichincha "NOTIFICACION BANCO PICHINCHA", "Realizaste una transferencia": sent from "Cuenta de
  origen" to "Cuenta destino Nombre"; or the beneficiary's copy ("Cuenta acreditada", "Nombre del
  ordenante").
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

PRODUBANCO = "Produbanco"
PICHINCHA = "Banco Pichincha"


@dataclass
class Notice:
    bank: str  # the bank of the household's account the money left or reached
    direction: str  # "sent" or "received"
    amount: Decimal  # positive
    our_last4: str | None  # None: the email doesn't say (Produbanco "enviada")
    other_party: str | None
    other_last4: str | None
    description: str | None
    reference: str | None
    day: date | None  # from the email text; the script also sends the email's date


def _flat(text: str) -> str:
    """Markdown tables and bold marks out, one space between words."""
    text = re.sub(r"\*{3,}", "XXXX", text)  # masked numbers: "******0800" -> "XXXX0800"
    text = re.sub(r"[*|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _amount(text: str | None) -> Decimal | None:
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


# Produbanco's labels, in any order: a value runs until the next one (or the closing words).
LABELS = (
    "Contacto:",
    "Enviada por:",
    "Beneficiario:",
    "Banco Destino:",
    "Banco Origen:",
    "Cuenta Destino:",
    "Cuenta Beneficiario:",
    "Monto:",
    "Descripción:",
    "Canal:",
    "Referencia:",
    "Fecha y Hora:",
    "Transacción:",
    "Atentamente",
    "Esta transacción",
)
_NEXT = "|".join(re.escape(x) for x in LABELS)


def _field(flat: str, label: str) -> str | None:
    m = re.search(rf"\b{re.escape(label)}:\s*(.*?)\s*(?={_NEXT}|$)", flat)
    value = m.group(1).strip() if m else ""
    return value or None


def _last4(value: str | None) -> str | None:
    m = re.search(r"(\d{4})\s*$", value or "")
    return m.group(1) if m else None


def _name(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", (value or "").strip(" .,"))
    return value[:100] or None


MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ),
        start=1,
    )
}


def _spanish_day(text: str) -> date | None:
    """ "8/Septiembre/2026 8:49" """
    m = re.search(r"(\d{1,2})/([A-Za-zé]+)/(\d{4})", text)
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))


def parse(subject: str, body: str) -> Notice | None:
    """The notice in one email, or None when it isn't a transfer notice this reads."""
    flat = _flat(body)
    subj = subject.strip().lower()
    if "produbanco" in subj and "transferencia" in subj:
        return _produbanco(subj, flat)
    if "pichincha" in subj and "transferencia" in flat.lower():
        return _pichincha(flat)
    return None


def _produbanco(subj: str, flat: str) -> Notice | None:
    amount = _amount((_field(flat, "Monto") or "").lstrip("$ "))
    if amount is None or amount <= 0:
        return None
    description = _field(flat, "Descripción")
    ref = re.search(r"Referencia:\s*(\d+)", flat)
    reference = ref.group(1) if ref else None
    day = _spanish_day(flat)
    sender = re.search(r"Te confirmamos que (.+?) ha realizado una transferencia", flat)
    if subj.startswith("transferencia enviada"):
        return Notice(
            PRODUBANCO,
            "sent",
            amount,
            None,
            _name(_field(flat, "Contacto")),
            _last4(_field(flat, "Cuenta Destino")),
            description,
            reference,
            day,
        )
    if "recibida en produbanco" in subj:
        return Notice(
            PRODUBANCO,
            "received",
            amount,
            _last4(_field(flat, "Cuenta Beneficiario")),
            _name(_field(flat, "Enviada por")),
            None,
            description,
            reference,
            day,
        )
    if "acreditada" in subj or "recibida desde produbanco" in subj:
        bank = _field(flat, "Banco Destino") or PRODUBANCO
        return Notice(
            PICHINCHA if "pichincha" in bank.lower() else PRODUBANCO,
            "received",
            amount,
            _last4(_field(flat, "Cuenta Destino")),
            _name(sender.group(1) if sender else None),
            None,
            description,
            reference,
            day,
        )
    return None


def _pichincha(flat: str) -> Notice | None:
    doc = re.search(r"Documento: Fecha:\s*(\d+)\s+(\d{2})/(\d{2})/(\d{4})", flat)
    if "Realizaste una transferencia" in flat:
        m = re.search(r"Monto: Concepto\s+([\d.,]+)\s*(.*?)\s*Cuenta de origen", flat)
        to = re.search(r"Cuenta destino Nombre: Número de cuenta:\s*(.+?)\s*X+(\d{4})", flat)
        origin = re.search(r"Cuenta de origen Número de cuenta:\s*X+(\d{4})", flat)
        amount = _amount(m.group(1)) if m else None
        if amount is None or amount <= 0:
            return None
        return Notice(
            PICHINCHA,
            "sent",
            amount,
            origin.group(1) if origin else None,
            _name(to.group(1)) if to else None,
            to.group(2) if to else None,
            (m.group(2) or None) if m else None,
            doc.group(1) if doc else None,
            date(int(doc.group(4)), int(doc.group(3)), int(doc.group(2))) if doc else None,
        )
    if "Cuenta acreditada" in flat:
        acc = re.search(r"Cuenta acreditada:\s*X+(\d{4})", flat)
        who = re.search(r"Nombre del ordenante:\s*(.+?)\s*Monto:", flat)
        m = re.search(r"Monto:\s*USD\s*([\d.,]+)", flat)
        concept = re.search(r"Concepto:\s*(.*?)\s*Número de documento:", flat)
        number = re.search(r"Número de documento:\s*(\d+)", flat)
        when = re.search(r"Fecha:\s*(\d{2})/(\d{2})/(\d{4})", flat)
        amount = _amount(m.group(1)) if m else None
        if amount is None or amount <= 0 or acc is None:
            return None
        return Notice(
            PICHINCHA,
            "received",
            amount,
            acc.group(1),
            _name(who.group(1)) if who else None,
            None,
            (concept.group(1) or None) if concept else None,
            number.group(1) if number else None,
            date(int(when.group(3)), int(when.group(2)), int(when.group(1))) if when else None,
        )
    return None
