"""Claude Haiku wrapper for NLP tasks: search intent extraction + language detection.

Uses Haiku for ~90% of calls (cost-efficient). See spec Section 9.
"""
import anthropic

_HAIKU_MODEL = "claude-haiku-4-5-latest"
_SUPPORTED_LANGUAGES = {"en", "es"}


class AIClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def extract_search_intent(self, text: str) -> str:
        """Extract product search query from natural language.

        Input: "How much are AirPods Pro right now?"
        Output: "AirPods Pro"
        """
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=100,
            system=(
                "Extract the product name or search query from the user's message. "
                "Return ONLY the product name/query, nothing else. "
                "If the message is not about a product, return the message as-is."
            ),
            messages=[{"role": "user", "content": text}],
        )
        return response.content[0].text.strip()

    async def detect_language(self, text: str) -> str:
        """Detect language of user's message. Returns 'en' or 'es'.

        Falls back to 'en' for unsupported languages.
        """
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=5,
            system=(
                "Detect the language of the user's message. "
                "Return ONLY the ISO 639-1 code (e.g., 'en', 'es'). Nothing else."
            ),
            messages=[{"role": "user", "content": text}],
        )
        lang = response.content[0].text.strip().lower()[:2]
        return lang if lang in _SUPPORTED_LANGUAGES else "en"
