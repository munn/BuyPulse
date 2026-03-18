"""Classify user input as product URL, product ID, or natural language query.

Detection order (per spec Section 2.2):
1. URL regex — contains amazon.com/dp/ or amazon.com/gp/product/
2. Product ID regex — standalone B[A-Z0-9]{9} (Amazon ASIN)
3. Everything else — natural language
"""
import re
from dataclasses import dataclass
from enum import Enum


class InputType(Enum):
    URL = "url"
    PRODUCT_ID = "product_id"
    NATURAL_LANGUAGE = "natural_language"


@dataclass(frozen=True)
class ParseResult:
    input_type: InputType
    platform_id: str | None = None
    platform: str = "amazon"
    query: str | None = None


_URL_PATTERN = re.compile(
    r"amazon\.com/(?:[\w-]+/)?(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE
)
_ASIN_PATTERN = re.compile(r"\bB[A-Z0-9]{9}\b")


def parse_input(text: str) -> ParseResult:
    """Classify and extract product identifier from user message."""
    url_match = _URL_PATTERN.search(text)
    if url_match:
        return ParseResult(
            InputType.URL, platform_id=url_match.group(1).upper(), platform="amazon",
        )
    asin_match = _ASIN_PATTERN.search(text)
    if asin_match:
        return ParseResult(
            InputType.PRODUCT_ID, platform_id=asin_match.group(0), platform="amazon",
        )
    return ParseResult(InputType.NATURAL_LANGUAGE, query=text.strip())
