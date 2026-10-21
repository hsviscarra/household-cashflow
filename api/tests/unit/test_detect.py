from datetime import date

import pytest

from app.ingestion.detect import PdfError, detect, read_pdf
from tests.fixtures import statements as s


@pytest.mark.parametrize(
    ("make", "source", "last4", "period"),
    [
        (s.bofa, "bofa", ["8872", "1862"], (date(2026, 8, 22), date(2026, 9, 22))),
        (s.capitalone, "capitalone", ["4003"], (date(2026, 9, 4), date(2026, 10, 3))),
        (s.pichincha, "pichincha", ["2829"], (date(2026, 6, 13), date(2026, 7, 12))),
        (s.produbanco, "produbanco", ["3721"], (date(2026, 7, 1), date(2026, 7, 31))),
        (s.diners, "diners", ["1234"], (date(2026, 6, 4), date(2026, 7, 3))),
        (s.unknown, "unknown", [], (None, None)),
    ],
)
def test_detects_source_last4_and_period(make, source, last4, period) -> None:  # type: ignore[no-untyped-def]
    info = read_pdf(make())
    found = detect(info.text)
    assert (found.source, found.last4, (found.period_start, found.period_end)) == (
        source,
        last4,
        period,
    )
    assert info.pages >= 1


def test_merchant_text_does_not_fool_detection() -> None:
    # A BofA statement paying Capital One mentions "CAPITAL ONE" but is still BofA.
    assert detect("CAPITAL ONE DES:MOBILE PMT\nbankofamerica.com").source == "bofa"


def test_unreadable_files() -> None:
    with pytest.raises(PdfError, match="not a PDF"):
        read_pdf(b"hello")
    with pytest.raises(PdfError, match="password-protected"):
        read_pdf(s.encrypted())
    with pytest.raises(PdfError, match="damaged"):
        read_pdf(b"%PDF-1.4 garbage")


def test_bad_dates_give_no_period() -> None:
    assert detect("produbanco.com Del 01 Xyz 2026 Al 31 Jul 2026").period_start is None
    assert detect("BANCO PICHINCHA C.A. 31/02/2026").period_start is None
