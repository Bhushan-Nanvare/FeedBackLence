"""Minimal GitHub REST client for reading repository issues."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

from app.errors import RateLimitedError

API_URL = "https://api.github.com"
PAGE_SIZE = 100
MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


@dataclass(frozen=True)
class GithubIssue:
    number: int
    url: str
    title: str
    body: str
    author_login: str
    author_is_maintainer: bool
    state: str
    state_reason: str | None
    labels: list[str]
    comments_count: int
    reactions_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "GithubIssue":
        user = raw.get("user") or {}
        return cls(
            number=raw["number"],
            url=raw["html_url"],
            title=raw["title"],
            body=raw.get("body") or "",
            author_login=user.get("login", "ghost"),
            author_is_maintainer=raw.get("author_association") in MAINTAINER_ASSOCIATIONS,
            state=raw["state"],
            state_reason=raw.get("state_reason"),
            labels=[
                label["name"] if isinstance(label, dict) else label
                for label in raw.get("labels", [])
            ],
            comments_count=raw.get("comments", 0),
            reactions_count=(raw.get("reactions") or {}).get("total_count", 0),
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=datetime.fromisoformat(raw["updated_at"]),
        )


class GithubClient:
    def __init__(
        self, token: str | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "FeedbackLens"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=API_URL, headers=headers, timeout=30.0, transport=transport
        )

    def __enter__(self) -> "GithubClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def iter_issue_pages(
        self,
        owner: str,
        repo: str,
        *,
        sort: Literal["created", "updated"],
        direction: Literal["asc", "desc"],
        since: datetime | None = None,
    ) -> Iterator[list[GithubIssue]]:
        """Yield issues one API page at a time, leaving out pull requests and bot accounts."""
        params: dict[str, str | int] | None = {
            "state": "all",
            "sort": sort,
            "direction": direction,
            "per_page": PAGE_SIZE,
        }
        if since is not None:
            params["since"] = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        url: str | None = f"/repos/{owner}/{repo}/issues"
        while url is not None:
            response = self._get(url, params)
            yield [GithubIssue.from_api(raw) for raw in response.json() if _is_user_issue(raw)]
            next_link = response.links.get("next")
            url = next_link["url"] if next_link else None
            params = None  # the "next" link already carries every query parameter

    def _get(self, url: str, params: dict[str, str | int] | None) -> httpx.Response:
        response = self._http.get(url, params=params)
        if response.status_code in (403, 429):
            reset_at = _rate_limit_reset(response)
            if reset_at is not None:
                raise RateLimitedError("GitHub", reset_at)
        response.raise_for_status()
        return response


def _is_user_issue(raw: dict[str, Any]) -> bool:
    # The issues endpoint also returns pull requests, and bot posts aren't user feedback.
    return "pull_request" not in raw and (raw.get("user") or {}).get("type") != "Bot"


def _rate_limit_reset(response: httpx.Response) -> datetime | None:
    if retry_after := response.headers.get("retry-after"):
        return datetime.now(UTC) + timedelta(seconds=int(retry_after))
    if response.headers.get("x-ratelimit-remaining") == "0":
        return datetime.fromtimestamp(int(response.headers["x-ratelimit-reset"]), UTC)
    return None
