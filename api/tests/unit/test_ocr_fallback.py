"""Any bank's statement without a text layer (a scan) is read with OCR and must still tie out."""

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.ingestion import ocr
from app.ingestion.detect import detect, read_pdf
from app.ingestion.parsers import PARSERS, produbanco
from app.ingestion.parsers.pacificard import parse as pacificard_parse
from tests.fixtures import statements as s
from tests.unit.test_pacificard_parser import NOISY

needs_ocr = pytest.mark.skipif(not ocr.available(), reason="tesseract is not installed")


@needs_ocr
@pytest.mark.parametrize(
    ("make", "source"),
    [
        (s.pichincha_full, "pichincha"),  # Ecuadorian numbers (1.024,14), trailing minus
        (s.diners_full, "diners"),  # accents dropped by OCR (PAGOS/CREDITOS)
        (s.capitalone_full, "capitalone"),  # dollar signs ($500.00)
        (s.bofa_full, "bofa"),
    ],
)
def test_scanned_statement_is_recognized_and_ties_out(
    make: Callable[[], bytes], source: str
) -> None:
    data = s.scanned(make())
    assert not read_pdf(data).text.strip()  # really no text layer
    found = detect(ocr.header_text(data))
    if found.source == "unknown":
        found = detect(ocr.header_text(data, whole=True))
    assert found.source == source
    parsed = PARSERS[source](ocr.ocr_pages(data))
    assert parsed.tieout_ok, ([c for c in parsed.checks if not c.ok], parsed.rejects)


@needs_ocr
def test_scanned_produbanco_uploads_reads_and_loads(client: TestClient) -> None:
    files = [("files", ("scan.pdf", s.scanned(s.produbanco_full()), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    # "produbanco.com" is in the footer: found by the whole-page read.
    assert st["source"] == "produbanco" and st["accounts"][0]["name"] == "Produbanco Ahorros Hernan"
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, [c for c in b["checks"] if not c["ok"]]
    assert client.post(f"/api/batches/{b['batch_id']}/approve").json()["loaded"] == 10


def test_produbanco_sign_lost_by_ocr_comes_from_the_balance() -> None:
    head = (
        "Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026\\n"
        "Saldo inicial contable: 100.00\\nSaldo final contable: 70.00\\n"
    )
    lines = "Quito Jul 2 1 DEBITO VISA 30.00 70.00 70.00"  # the "-" was not read
    p = produbanco.parse([head + lines])
    assert p.tieout_ok and p.lines[0].amount == Decimal("-30.00")


def test_tied_printings_are_settled_by_the_lines() -> None:
    # The detail and the summary box disagree on the previous balance: one of them balances.
    text = NOISY.replace("s44444 32LDO ANTERIOR 400.00", "s44444 32LDO ANTERIOR 480.00")
    p = pacificard_parse([text])
    assert p.opening_balance == Decimal("400.00") and p.tieout_ok
    # Neither printed value balances: it stays a failed check, never a made-up number.
    worse = text.replace("400.00 148.85", "460.00 148.85")
    assert not pacificard_parse([worse]).tieout_ok
