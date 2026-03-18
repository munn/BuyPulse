"""SiliconFlow LLM wrapper for NLP tasks: search intent extraction + language detection.

Uses Qwen2.5-32B via SiliconFlow API (OpenAI-compatible).
Language detection uses langdetect (zero LLM cost).
"""
from openai import AsyncOpenAI

from langdetect import detect as _langdetect
from langdetect import LangDetectException

_MODEL = "Qwen/Qwen2.5-32B-Instruct"
_SUPPORTED_LANGUAGES = {"en", "es"}

_SEARCH_INTENT_PROMPT = (
    "Extract product name(s) from the user's message for Amazon price lookup.\n"
    "Rules:\n"
    "1. Return ONLY product name(s), no explanation\n"
    "2. Fix typos to canonical names (roobma→Roomba, samsnug→Samsung, airpod→AirPods)\n"
    "3. Always return in English, even if message is in another language\n"
    "4. Comparisons (X vs Y, X or Y): return comma-separated list: \"Product1, Product2\"\n"
    "5. Strip modifiers (under $300, cheapest, best, new) — keep only product identity\n"
    "6. Vague shopping intent → extract as search query\n"
    "7. No shopping intent → NONE"
)


class AIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1") -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def extract_search_intent(self, text: str) -> str:
        """Extract product search query from natural language.

        Input: "How much are AirPods Pro right now?"
        Output: "AirPods Pro"
        """
        response = await self._client.chat.completions.create(
            model=_MODEL,
            max_tokens=100,
            temperature=0,
            messages=[
                {"role": "system", "content": _SEARCH_INTENT_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def detect_language(self, text: str) -> str:
        """Detect language of user's message. Returns 'en' or 'es'.

        Uses langdetect (no LLM call). Falls back to 'en' for unsupported languages.
        """
        try:
            lang = _langdetect(text)[:2]
        except LangDetectException:
            return "en"
        return lang if lang in _SUPPORTED_LANGUAGES else "en"
