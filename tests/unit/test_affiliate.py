"""Tests for affiliate link generation."""
from cps.services.affiliate import build_product_link, build_search_link


def test_product_link():
    url = build_product_link("B08N5WRWNW", "buypulse-20")
    assert url == "https://www.amazon.com/dp/B08N5WRWNW?tag=buypulse-20"


def test_search_link():
    url = build_search_link("airpods pro", "buypulse-20")
    assert "amazon.com/s?" in url
    assert "tag=buypulse-20" in url
    assert "airpods" in url.lower()


def test_search_link_encodes_spaces():
    url = build_search_link("robot vacuum cleaner", "tag1")
    assert " " not in url.split("?")[1]  # query params should be encoded
