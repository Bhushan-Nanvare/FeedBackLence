"""Gemini implementations of the text and embedding interfaces."""

import math
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.genai import errors, types

from app.ai.embeddings import EMBEDDING_DIMENSIONS, EmbeddingResult, check_dimensions
from app.ai.llm import LLMResult
from app.errors import PermanentJobError, RateLimitedError

DEFAULT_RETRY_DELAY = timedelta(seconds=60)
DAILY_QUOTA_RETRY_DELAY = timedelta(hours=1)
# The request itself is wrong (bad key, unknown model, invalid schema): retrying won't help.
PERMANENT_ERROR_CODES = frozenset({400, 401, 403, 404})


class RateLimiter:
    """Spaces requests evenly to stay under a per-minute quota.

    Each worker process keeps its own pace, so the setting should allow for how many run.
    """

    def __init__(
        self,
        requests_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = 60.0 / requests_per_minute
        self._clock = clock
        self._sleep = sleep
        self._next_request_at = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next_request_at:
            self._sleep(self._next_request_at - now)
        self._next_request_at = max(now, self._next_request_at) + self._min_interval


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        requests_per_minute: int,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._client = client or genai.Client(api_key=api_key)
        self._limiter = RateLimiter(requests_per_minute, clock, sleep)
        self._clock = clock

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> LLMResult:
        self._limiter.wait()
        started = self._clock()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                ),
            )
        except errors.APIError as exc:
            translated = _translate_error(exc)
            if translated is exc:
                raise
            raise translated from exc

        usage = response.usage_metadata
        return LLMResult(
            text=response.text or "",
            model=self.model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage
                else 0
            ),
            latency_ms=round((self._clock() - started) * 1000),
        )


class GeminiEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        requests_per_minute: int,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._client = client or genai.Client(api_key=api_key)
        self._limiter = RateLimiter(requests_per_minute, clock, sleep)
        self._clock = clock

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self._limiter.wait()
        started = self._clock()
        try:
            response = self._client.models.embed_content(
                model=self.model,
                contents=list(texts),
                config=types.EmbedContentConfig(
                    task_type="CLUSTERING", output_dimensionality=EMBEDDING_DIMENSIONS
                ),
            )
        except errors.APIError as exc:
            translated = _translate_error(exc)
            if translated is exc:
                raise
            raise translated from exc

        # Shortened vectors lose their unit length, which Google asks callers to restore.
        vectors = [_to_unit_length(list(item.values or [])) for item in response.embeddings or []]
        check_dimensions(vectors, self.model)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            input_tokens=_billable_characters(response),
            latency_ms=round((self._clock() - started) * 1000),
        )


def _to_unit_length(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


def _billable_characters(response: Any) -> int:
    metadata = getattr(response, "metadata", None)
    return getattr(metadata, "billable_character_count", None) or 0


def _translate_error(exc: errors.APIError) -> Exception:
    if exc.code == 429:
        return RateLimitedError("Gemini", datetime.now(UTC) + _retry_delay(exc.details))
    if exc.code in PERMANENT_ERROR_CODES:
        return PermanentJobError(
            f"Gemini rejected the request ({exc.code} {exc.status}): {exc.message}"
        )
    return exc


def _retry_delay(details: Any) -> timedelta:
    """Read how long Gemini asks us to wait from a 429 error body."""
    error = details.get("error", details) if isinstance(details, dict) else {}
    retry_delay = DEFAULT_RETRY_DELAY
    for detail in error.get("details") or []:
        if not isinstance(detail, dict):
            continue
        # A used-up daily quota won't recover in seconds, whatever RetryInfo says.
        if "PerDay" in str(detail.get("violations", "")):
            return DAILY_QUOTA_RETRY_DELAY
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                retry_delay = timedelta(seconds=float(match.group(1)))
    return retry_delay
