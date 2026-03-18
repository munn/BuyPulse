# src/cps/platforms/registry.py
"""Platform plugin registry — factory functions for fetchers and parsers."""

from pathlib import Path

from cps.platforms.protocol import PlatformFetcher, PlatformParser


def get_fetcher(platform: str, **kwargs: object) -> PlatformFetcher:
    """Create the appropriate fetcher for a platform."""
    if platform == "amazon":
        from cps.platforms.amazon.fetcher import AmazonFetcher
        return AmazonFetcher(
            base_url=str(kwargs["base_url"]),
            data_dir=Path(str(kwargs["data_dir"])),
            rate_limit=float(kwargs.get("rate_limit", 1.0)),
        )
    raise ValueError(f"Unknown platform: {platform}")


def get_parser(platform: str) -> PlatformParser:
    """Create the appropriate parser for a platform."""
    if platform == "amazon":
        from cps.platforms.amazon.parser import AmazonParser
        return AmazonParser()
    raise ValueError(f"Unknown platform: {platform}")
