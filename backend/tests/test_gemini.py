from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.ai.gemini import GeminiClient
from app.ai.llm import get_llm_client
from app.config import Settings
from app.errors import PermanentJobError, RateLimitedError

OK_RESPONSE = SimpleNamespace(
    text='{"results": []}',
    usage_metadata=SimpleNamespace(
        prompt_token_count=120, candidates_token_count=30, thoughts_token_count=12
    ),
)


class FakeModels:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_client(outcome: Any, **options: Any) -> tuple[GeminiClient, FakeModels]:
    models = FakeModels(outcome)
    client = GeminiClient(
        api_key="unused",
        model="gemini-test",
        requests_per_minute=options.pop("requests_per_minute", 6000),
        client=SimpleNamespace(models=models),
        **options,
    )
    return client, models


def generate(client: GeminiClient) -> Any:
    return client.generate_json(
        system="Label things.", prompt="Items: []", schema={"type": "object"}
    )


def api_error(code: int, details: list[dict[str, Any]] | None = None) -> errors.APIError:
    body = {
        "error": {"code": code, "status": "ERROR", "message": "failed", "details": details or []}
    }
    error_class = errors.ServerError if code >= 500 else errors.ClientError
    return error_class(code, body)


def test_returns_text_and_token_usage() -> None:
    client, models = make_client(OK_RESPONSE)

    result = generate(client)

    assert (result.text, result.model) == ('{"results": []}', "gemini-test")
    # Thinking tokens are billed as output, so they count towards output tokens.
    assert (result.input_tokens, result.output_tokens) == (120, 42)
    call = models.calls[0]
    assert (call["model"], call["contents"]) == ("gemini-test", "Items: []")
    assert call["config"].system_instruction == "Label things."
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_json_schema == {"type": "object"}


def test_rate_limit_waits_as_long_as_gemini_asks() -> None:
    retry_info = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}
    client, _ = make_client(api_error(429, [retry_info]))

    with pytest.raises(RateLimitedError) as exc_info:
        generate(client)

    expected = datetime.now(UTC) + timedelta(seconds=37)
    assert abs(exc_info.value.reset_at - expected) < timedelta(seconds=5)


def test_used_up_daily_quota_waits_an_hour() -> None:
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
        },
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20s"},
    ]
    client, _ = make_client(api_error(429, details))

    with pytest.raises(RateLimitedError) as exc_info:
        generate(client)

    expected = datetime.now(UTC) + timedelta(hours=1)
    assert abs(exc_info.value.reset_at - expected) < timedelta(seconds=5)


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_request_errors_fail_permanently(code: int) -> None:
    client, _ = make_client(api_error(code))

    with pytest.raises(PermanentJobError):
        generate(client)


def test_server_errors_are_raised_so_the_job_retries() -> None:
    client, _ = make_client(api_error(503))

    with pytest.raises(errors.ServerError):
        generate(client)


def test_spaces_requests_to_respect_the_rate_limit() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client, _ = make_client(OK_RESPONSE, requests_per_minute=30, clock=lambda: now[0], sleep=sleep)

    generate(client)
    generate(client)
    now[0] += 0.5
    generate(client)

    assert sleeps == [2.0, 1.5]


def test_llm_client_requires_an_api_key() -> None:
    with pytest.raises(PermanentJobError, match="GEMINI_API_KEY"):
        get_llm_client(Settings(gemini_api_key=None))

    client = get_llm_client(Settings(gemini_api_key="test-key", gemini_model="gemini-x"))
    assert client.model == "gemini-x"
