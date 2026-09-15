"""Provider-neutral interface for the AI calls FeedbackLens makes."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.errors import PermanentJobError


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class LLMClient(Protocol):
    model: str

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> LLMResult:
        """Return JSON text that matches `schema`."""
        ...


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise PermanentJobError("GEMINI_API_KEY is not set. Add it to .env and run the job again.")

    # Imported here because the SDK is slow to import and only the worker needs it.
    from app.ai.gemini import GeminiClient

    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        requests_per_minute=settings.gemini_requests_per_minute,
    )
