"""Gemini implementation of LLMClient."""

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.genai import errors, types

from app.ai.llm import LLMResult
from app.errors import PermanentJobError, RateLimitedError

DEFAULT_RETRY_DELAY = timedelta(seconds=60)
DAILY_QUOTA_RETRY_DELAY = timedelta(hours=1)
# The request itself is wrong (bad key, unknown model, invalid schema): retrying won't help.
PERMANENT_ERROR_CODES = frozenset({400, 401, 403, 404})


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
        self._min_interval = 60.0 / requests_per_minute
        self._clock = clock
        self._sleep = sleep
        self._next_request_at = 0.0

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> LLMResult:
        self._wait_for_rate_limit()
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

    def _wait_for_rate_limit(self) -> None:
        # Space requests evenly to stay under the per-minute quota. Each worker process
        # keeps its own pace, so the setting should allow for the number of workers.
        now = self._clock()
        if now < self._next_request_at:
            self._sleep(self._next_request_at - now)
        self._next_request_at = max(now, self._next_request_at) + self._min_interval


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
