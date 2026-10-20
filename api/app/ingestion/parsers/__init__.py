"""Statement parsers by source. Each takes the PDF's page texts and returns ParsedStatement."""

from collections.abc import Callable

from app.ingestion.parsers import bofa, capitalone
from app.ingestion.parsers.base import ParsedStatement

PARSERS: dict[str, Callable[[list[str]], ParsedStatement]] = {
    bofa.NAME: bofa.parse,
    capitalone.NAME: capitalone.parse,
}
