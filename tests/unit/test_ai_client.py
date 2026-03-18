"""Tests for AI client — mocked OpenAI API calls + langdetect."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.ai.client import AIClient


@pytest.fixture
def client():
    return AIClient(api_key="test-key", base_url="https://api.test.com/v1")


class TestExtractSearchIntent:
    async def test_extracts_product_query(self, client):
        mock_choice = MagicMock()
        mock_choice.message.content = "AirPods Pro"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.extract_search_intent("How much are AirPods Pro right now?")
            assert result == "AirPods Pro"

    async def test_uses_qwen_model(self, client):
        mock_choice = MagicMock()
        mock_choice.message.content = "test"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            await client.extract_search_intent("test query")
            call_kwargs = mock_create.call_args.kwargs
            assert "Qwen" in call_kwargs["model"]

    async def test_returns_none_for_no_intent(self, client):
        mock_choice = MagicMock()
        mock_choice.message.content = "NONE"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.extract_search_intent("hello")
            assert result == "NONE"

    async def test_handles_empty_content(self, client):
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.extract_search_intent("test")
            assert result == ""

    async def test_prompt_includes_typo_correction(self, client):
        mock_choice = MagicMock()
        mock_choice.message.content = "test"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            await client.extract_search_intent("test")
            messages = mock_create.call_args.kwargs["messages"]
            system_msg = messages[0]["content"]
            assert "Fix typos" in system_msg
            assert "NONE" in system_msg


class TestDetectLanguage:
    def test_detects_english(self, client):
        with patch("cps.ai.client._langdetect", return_value="en"):
            result = client.detect_language("What's the price of this?")
            assert result == "en"

    def test_detects_spanish(self, client):
        with patch("cps.ai.client._langdetect", return_value="es"):
            result = client.detect_language("Cuanto cuesta esto?")
            assert result == "es"

    def test_falls_back_to_en_for_unsupported(self, client):
        with patch("cps.ai.client._langdetect", return_value="fr"):
            result = client.detect_language("Bonjour")
            assert result == "en"

    def test_falls_back_to_en_on_exception(self, client):
        from langdetect import LangDetectException

        with patch("cps.ai.client._langdetect", side_effect=LangDetectException(0, "")):
            result = client.detect_language("")
            assert result == "en"
