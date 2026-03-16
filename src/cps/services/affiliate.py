"""Amazon affiliate link builder — every user-facing URL carries the tag."""
from urllib.parse import quote_plus


def build_product_link(asin: str, tag: str) -> str:
    """Build tagged product URL: https://www.amazon.com/dp/{ASIN}?tag={tag}."""
    return f"https://www.amazon.com/dp/{asin}?tag={tag}"


def build_search_link(query: str, tag: str) -> str:
    """Build tagged search URL for fallback tier."""
    return f"https://www.amazon.com/s?k={quote_plus(query)}&tag={tag}"
