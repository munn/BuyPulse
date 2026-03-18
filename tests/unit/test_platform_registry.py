# tests/unit/test_platform_registry.py
"""Tests for platform registry — factory functions."""

from pathlib import Path

import pytest

from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.amazon.parser import AmazonParser
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.platforms.registry import get_fetcher, get_parser


class TestGetFetcher:
    def test_amazon_returns_amazon_fetcher(self, tmp_path):
        fetcher = get_fetcher(
            "amazon",
            base_url="https://charts.example.com",
            data_dir=tmp_path,
        )
        assert isinstance(fetcher, AmazonFetcher)
        assert isinstance(fetcher, PlatformFetcher)

    def test_amazon_passes_rate_limit(self, tmp_path):
        fetcher = get_fetcher(
            "amazon",
            base_url="https://charts.example.com",
            data_dir=tmp_path,
            rate_limit=2.5,
        )
        assert isinstance(fetcher, AmazonFetcher)

    def test_unknown_platform_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_fetcher("ebay", base_url="x", data_dir=tmp_path)


class TestGetParser:
    def test_amazon_returns_amazon_parser(self):
        parser = get_parser("amazon")
        assert isinstance(parser, AmazonParser)
        assert isinstance(parser, PlatformParser)

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_parser("ebay")
