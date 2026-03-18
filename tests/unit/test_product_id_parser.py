"""Tests for input classification: URL → product ID → natural language."""
from cps.services.product_id_parser import InputType, ParseResult, parse_input


class TestUrlParsing:
    def test_standard_dp_url(self):
        result = parse_input("https://www.amazon.com/dp/B08N5WRWNW")
        assert result == ParseResult(InputType.URL, platform_id="B08N5WRWNW", platform="amazon")

    def test_gp_product_url(self):
        result = parse_input("https://amazon.com/gp/product/B09V3KXJPB?tag=foo")
        assert result == ParseResult(InputType.URL, platform_id="B09V3KXJPB", platform="amazon")

    def test_url_with_surrounding_text(self):
        result = parse_input("check this https://amazon.com/dp/B08N5WRWNW please")
        assert result == ParseResult(InputType.URL, platform_id="B08N5WRWNW", platform="amazon")

    def test_short_url_with_dp(self):
        result = parse_input("https://www.amazon.com/Some-Product-Name/dp/B0BSHF7WHW/ref=sr_1_1")
        assert result == ParseResult(InputType.URL, platform_id="B0BSHF7WHW", platform="amazon")


class TestProductIdParsing:
    def test_plain_product_id(self):
        result = parse_input("B08N5WRWNW")
        assert result == ParseResult(InputType.PRODUCT_ID, platform_id="B08N5WRWNW", platform="amazon")

    def test_product_id_with_text(self):
        # Per spec: product ID regex matches first, ignore rest of text
        result = parse_input("B08N5WRWNW is it a good price?")
        assert result == ParseResult(InputType.PRODUCT_ID, platform_id="B08N5WRWNW", platform="amazon")

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

    def test_url_takes_priority_over_product_id(self):
        # URL in text that also contains a standalone product ID pattern
        result = parse_input("https://amazon.com/dp/B08N5WRWNW B09V3KXJPB")
        assert result.input_type == InputType.URL
        assert result.platform_id == "B08N5WRWNW"
