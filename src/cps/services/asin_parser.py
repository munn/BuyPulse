"""Classify user input as Amazon URL, ASIN, or natural language query.

Detection order (per spec Section 2.2):
1. URL regex — contains amazon.com/dp/ or amazon.com/gp/product/
2. ASIN regex — standalone B[A-Z0-9]{9}
3. Everything else — natural language
"""
import re
from dataclasses import dataclass
from enum import Enum


class InputType(Enum):
    URL = "url"
    ASIN = "asin"
    NATURAL_LANGUAGE = "natural_language"


@dataclass(frozen=True)
class ParseResult:
    input_type: InputType
    asin: str | None = None
    query: str | None = None


_URL_PATTERN = re.compile(
    r"amazon\.com/(?:[\w-]+/)?(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE
)
_ASIN_PATTERN = re.compile(r"\bB[A-Z0-9]{9}\b")


def parse_input(text: str) -> ParseResult:
    """Classify and extract product identifier from user message."""
    # 1. URL regex
    url_match = _URL_PATTERN.search(text)
    if url_match:
        return ParseResult(InputType.URL, asin=url_match.group(1).upper())

    # 2. ASIN regex
    asin_match = _ASIN_PATTERN.search(text)
    if asin_match:
        return ParseResult(InputType.ASIN, asin=asin_match.group(0))

    # 3. Natural language
    return ParseResult(InputType.NATURAL_LANGUAGE, query=text.strip())
