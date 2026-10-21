"""Statement parsers by source. Each takes the PDF's page texts and returns ParsedStatement."""

from collections.abc import Callable

from PIL.Image import Image

from app.ingestion.ocr import first_page
from app.ingestion.parsers import bofa, capitalone, diners, pacificard, pichincha, produbanco
from app.ingestion.parsers.base import ParsedStatement

PARSERS: dict[str, Callable[[list[str]], ParsedStatement]] = {
    bofa.NAME: bofa.parse,
    capitalone.NAME: capitalone.parse,
    diners.NAME: diners.parse,
    pacificard.NAME: pacificard.parse,
    pichincha.NAME: pichincha.parse,
    produbanco.NAME: produbanco.parse,
}

# Sources whose PDFs are pictures, read with OCR: the part of each picture worth reading.
OCR_SOURCES: dict[str, Callable[[Image], Image]] = {pacificard.NAME: first_page}
