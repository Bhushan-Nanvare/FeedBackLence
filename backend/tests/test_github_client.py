from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.errors import RateLimitedError
from app.sources.github_client import GithubClient


def api_issue(number: int, **overrides: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "number": number,
        "html_url": f"https://github.com/acme/app/issues/{number}",
        "title": f"Issue {number}",
        "body": "Something broke",
        "user": {"login": f"user{number}", "type": "User"},
        "author_association": "NONE",
        "state": "open",
        "state_reason": None,
        "labels": [{"name": "bug"}],
        "comments": 2,
        "reactions": {"total_count": 3},
        "created_at": "2026-09-10T10:00:00Z",
        "updated_at": "2026-09-11T10:00:00Z",
    }
    issue.update(overrides)
    return issue


def fetch_all(handler: Any, **kwargs: Any) -> list[list[Any]]:
    with GithubClient(token=kwargs.pop("token", None), transport=httpx.MockTransport(handler)) as c:
        return list(c.iter_issue_pages("acme", "app", **kwargs))


def test_follows_pagination_and_skips_pull_requests_and_bots() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[api_issue(3)])
        return httpx.Response(
            200,
            json=[
                api_issue(1),
                api_issue(2, pull_request={"url": "https://api.github.com/pulls/2"}),
                api_issue(4, user={"login": "helper[bot]", "type": "Bot"}),
            ],
            headers={"Link": '<https://api.github.com/repositories/1/issues?page=2>; rel="next"'},
        )

    pages = fetch_all(handler, sort="created", direction="desc")

    assert [[issue.number for issue in page] for page in pages] == [[1], [3]]
    assert requests[0].url.path == "/repos/acme/app/issues"
    assert requests[0].url.params["state"] == "all"
    assert requests[0].url.params["sort"] == "created"
    assert requests[0].url.params["direction"] == "desc"
    assert str(requests[1].url) == "https://api.github.com/repositories/1/issues?page=2"


def test_parses_issue_fields() -> None:
    raw = api_issue(
        7, author_association="MEMBER", body=None, state="closed", state_reason="duplicate"
    )

    pages = fetch_all(
        lambda request: httpx.Response(200, json=[raw]), sort="updated", direction="asc"
    )
    issue = pages[0][0]

    assert issue.author_is_maintainer is True
    assert issue.body == ""
    assert issue.labels == ["bug"]
    assert (issue.comments_count, issue.reactions_count) == (2, 3)
    assert (issue.state, issue.state_reason) == ("closed", "duplicate")
    assert issue.created_at == datetime(2026, 9, 10, 10, tzinfo=UTC)


def test_sends_since_and_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    fetch_all(
        handler,
        token="secret-token",
        sort="updated",
        direction="asc",
        since=datetime(2026, 9, 1, 8, 30, tzinfo=UTC),
    )

    assert requests[0].url.params["since"] == "2026-09-01T08:30:00Z"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"


def test_primary_rate_limit_raises_with_reset_time() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1788000000"},
            json={"message": "API rate limit exceeded"},
        )

    with pytest.raises(RateLimitedError) as exc_info:
        fetch_all(handler, sort="created", direction="desc")

    assert exc_info.value.reset_at == datetime.fromtimestamp(1788000000, UTC)


def test_secondary_rate_limit_uses_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "60"})

    with pytest.raises(RateLimitedError) as exc_info:
        fetch_all(handler, sort="created", direction="desc")

    expected = datetime.now(UTC) + timedelta(seconds=60)
    assert abs(exc_info.value.reset_at - expected) < timedelta(seconds=5)


@pytest.mark.parametrize("status_code", [403, 404, 500])
def test_other_errors_are_raised(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "nope"})

    with pytest.raises(httpx.HTTPStatusError):
        fetch_all(handler, sort="created", direction="desc")
