"""Tests for AI client — mocked Anthropic API calls."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.ai.client import AIClient


@pytest.fixture
def client():
    return AIClient(api_key="test-key")


class TestExtractSearchIntent:
    async def test_extracts_product_query(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="AirPods Pro")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.extract_search_intent("How much are AirPods Pro right now?")
            assert result == "AirPods Pro"

    async def test_uses_haiku_model(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ) as mock_create:
            await client.extract_search_intent("test query")
            call_kwargs = mock_create.call_args.kwargs
            assert "haiku" in call_kwargs["model"]


class TestDetectLanguage:
    async def test_detects_english(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="en")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("What's the price of this?")
            assert result == "en"

    async def test_detects_spanish(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="es")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("Cuanto cuesta esto?")
            assert result == "es"

    async def test_falls_back_to_en(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="fr")]  # unsupported
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("Bonjour")
            assert result == "en"  # fallback
