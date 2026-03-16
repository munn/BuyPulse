"""Tests for input classification: URL → ASIN → natural language."""
from cps.services.asin_parser import InputType, ParseResult, parse_input


class TestUrlParsing:
    def test_standard_dp_url(self):
        result = parse_input("https://www.amazon.com/dp/B08N5WRWNW")
        assert result == ParseResult(InputType.URL, asin="B08N5WRWNW")

    def test_gp_product_url(self):
        result = parse_input("https://amazon.com/gp/product/B09V3KXJPB?tag=foo")
        assert result == ParseResult(InputType.URL, asin="B09V3KXJPB")

    def test_url_with_surrounding_text(self):
        result = parse_input("check this https://amazon.com/dp/B08N5WRWNW please")
        assert result == ParseResult(InputType.URL, asin="B08N5WRWNW")

    def test_short_url_with_dp(self):
        result = parse_input("https://www.amazon.com/Some-Product-Name/dp/B0BSHF7WHW/ref=sr_1_1")
        assert result == ParseResult(InputType.URL, asin="B0BSHF7WHW")


class TestAsinParsing:
    def test_plain_asin(self):
        result = parse_input("B08N5WRWNW")
        assert result == ParseResult(InputType.ASIN, asin="B08N5WRWNW")

    def test_asin_with_text(self):
        # Per spec: ASIN regex matches first, ignore rest of text
        result = parse_input("B08N5WRWNW is it a good price?")
        assert result == ParseResult(InputType.ASIN, asin="B08N5WRWNW")

    def test_non_b_prefix_not_matched(self):
        # Only B-prefix ASINs matched as standalone
        result = parse_input("A08N5WRWNW")
        assert result.input_type == InputType.NATURAL_LANGUAGE


class TestNaturalLanguage:
    def test_simple_query(self):
        result = parse_input("How much are AirPods Pro?")
        assert result == ParseResult(InputType.NATURAL_LANGUAGE, query="How much are AirPods Pro?")

    def test_empty_after_strip(self):
        result = parse_input("   ")
        assert result == ParseResult(InputType.NATURAL_LANGUAGE, query="")

    def test_url_takes_priority_over_asin(self):
        # URL in text that also contains a standalone ASIN pattern
        result = parse_input("https://amazon.com/dp/B08N5WRWNW B09V3KXJPB")
        assert result.input_type == InputType.URL
        assert result.asin == "B08N5WRWNW"
