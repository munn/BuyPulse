"""Affiliate link builder — every user-facing URL carries the tag."""
from urllib.parse import quote_plus


def build_product_link(platform_id: str, tag: str, platform: str = "amazon") -> str:
    """Build tagged product URL for the given platform.

    Raises:
        ValueError: If platform is not recognized.
    """
    if platform == "amazon":
        return f"https://www.amazon.com/dp/{platform_id}?tag={tag}"
    raise ValueError(f"Unknown platform: '{platform}'. Cannot build product link.")


def build_search_link(query: str, tag: str) -> str:
    """Build tagged search URL for fallback tier."""
    return f"https://www.amazon.com/s?k={quote_plus(query)}&tag={tag}"
