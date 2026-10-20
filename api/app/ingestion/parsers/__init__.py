"""Statement parsers by source. Each takes the PDF's page texts and returns ParsedStatement."""

from collections.abc import Callable

from app.ingestion.parsers import capitalone
from app.ingestion.parsers.base import ParsedStatement

PARSERS: dict[str, Callable[[list[str]], ParsedStatement]] = {
    capitalone.NAME: capitalone.parse,
}
