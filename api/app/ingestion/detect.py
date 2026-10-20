"""Read a statement PDF just enough to know whose it is (F3).

Detection looks for each bank's fingerprint text, the last four digits of the account or card and,
where the layout makes it easy, the statement period. Parsing every line is each parser's job
(F4 to F8). Nothing read here is stored except the source, the last four digits and the period:
names, addresses, cédula and full account numbers stay in the file.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

PAGES_TO_READ = 3

SOURCES = {
    "bofa": "Bank of America",
    "capitalone": "Capital One",
    "pichincha": "Banco Pichincha",
    "produbanco": "Produbanco",
    "diners": "Diners Club",
    "unknown": "Unknown format",
}

ES_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}  # fmt: skip


class PdfError(Exception):
    """The file can't be read as a PDF (not a PDF, damaged or password-protected)."""


@dataclass
class PdfInfo:
    pages: int
    text: str


@dataclass
class Detection:
    source: str
    last4: list[str] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None

    @property
    def label(self) -> str:
        return SOURCES[self.source]


def read_pdf(data: bytes) -> PdfInfo:
    if not data.startswith(b"%PDF-"):
        raise PdfError("This file is not a PDF.")
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            pages = len(pdf.pages)
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:PAGES_TO_READ])
    except (PdfminerException, PDFPasswordIncorrect, PDFSyntaxError, ValueError, KeyError) as exc:
        # pdfplumber wraps pdfminer errors; the original is its first argument.
        cause = exc.args[0] if isinstance(exc, PdfminerException) and exc.args else exc
        if isinstance(cause, PDFPasswordIncorrect):
            raise PdfError(
                "This PDF is password-protected. Open it, save or print it as a PDF without a "
                "password, and upload that copy."
            ) from exc
        raise PdfError("This PDF could not be read; it may be damaged.") from exc
    return PdfInfo(pages=pages, text=text)


def read_pages(data: bytes) -> list[str]:
    """Every page's text, for the parsers."""
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            return [p.extract_text() or "" for p in pdf.pages]
    except (PdfminerException, PDFSyntaxError, ValueError, KeyError) as exc:
        raise PdfError("This PDF could not be read; it may be damaged.") from exc


# ---------------- period parsers ----------------
def _en(fmt: str) -> Callable[[str], date]:
    return lambda s: datetime.strptime(" ".join(s.split()), fmt).date()


def _es(s: str) -> date:
    day, mon, year = s.split()
    return date(int(year), ES_MONTHS[mon[:3].lower()], int(day))


def _dmy(s: str) -> date:
    d, m, y = s.split("/")
    return date(int(y), int(m), int(d))


def _period(
    text: str, pattern: str, conv: Callable[[str], date]
) -> tuple[date | None, date | None]:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None, None
    try:
        a, b = conv(m.group(1)), conv(m.group(2))
    except (ValueError, KeyError):
        return None, None
    return (a, b) if a <= b else (b, a)


def _pichincha_period(text: str) -> tuple[date | None, date | None]:
    # "PERÍODO DESDE / PERÍODO HASTA" print as two dd/mm/yyyy dates on the summary page.
    found: list[date] = []
    for raw in re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", text):
        try:
            d = _dmy(raw)
        except ValueError:
            continue
        if d not in found:
            found.append(d)
        if len(found) == 2:
            return min(found), max(found)
    return None, None


@dataclass(frozen=True)
class Fingerprint:
    source: str
    # Any of these (case-insensitive) identifies the bank. Only domains and legal names: merchant
    # lines such as "CAPITAL ONE MOBILE PMT" on a BofA statement must not match.
    marks: tuple[str, ...]
    last4: str  # regex with one group: the last four digits
    period: Callable[[str], tuple[date | None, date | None]]


FINGERPRINTS = (
    Fingerprint(
        "capitalone",
        ("capitalone.com",),
        r"ending in (\d{4})",
        lambda t: _period(t, r"(\w{3} \d{1,2}, \d{4}) - (\w{3} \d{1,2}, \d{4})", _en("%b %d, %Y")),
    ),
    Fingerprint(
        "bofa",
        ("bankofamerica.com", "bank of america, n.a."),
        r"\b\d{4} \d{4} (\d{4})\b",
        lambda t: _period(t, r"for (\w+ \d{1,2}, \d{4}) to (\w+ \d{1,2}, \d{4})", _en("%B %d, %Y")),
    ),
    Fingerprint(
        "pichincha",
        ("banco pichincha c.a.", "pichincha.com"),
        r"\d{4,6}X{4,8}(\d{4})",
        _pichincha_period,
    ),
    Fingerprint(
        "produbanco",
        ("produbanco.com", "banco de la producción", "banco de la produccion"),
        r"CUENTA:\s*\d*(\d{4})\b",
        lambda t: _period(t, r"Del (\d{1,2} \w{3} \d{4}) Al (\d{1,2} \w{3} \d{4})", _es),
    ),
    Fingerprint(
        "diners",
        ("dinersclub", "diners club"),
        r"(?:X|\*){4,}\s?(\d{4})",
        lambda t: (None, None),
    ),
)


def detect(text: str) -> Detection:
    low = text.lower()
    for fp in FINGERPRINTS:
        if any(mark in low for mark in fp.marks):
            last4 = list(dict.fromkeys(re.findall(fp.last4, text, re.IGNORECASE)))
            start, end = fp.period(text)
            return Detection(fp.source, last4, start, end)
    return Detection("unknown")
