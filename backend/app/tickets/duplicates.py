"""Check whether the target repository already has an issue about this.

Filing the same thing twice is worse than not filing at all, so a draft carries the existing
issues that look like it and a person decides.
"""

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from app.ai.embeddings import Embedder
from app.sources.github_client import GithubIssue
from app.themes.vectors import unit_vectors

DEFAULT_CANDIDATES = 3
WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class DuplicateCandidate:
    number: int
    title: str
    url: str
    similarity: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class IssuePager(Protocol):
    def iter_issue_pages(
        self, owner: str, repo: str, *, sort: str, direction: str, since: Any = None
    ) -> Any: ...


def fetch_recent_issues(client: IssuePager, repo: str, *, limit: int) -> list[GithubIssue]:
    owner, name = repo.split("/", 1)
    found: list[GithubIssue] = []
    for page in client.iter_issue_pages(owner, name, sort="created", direction="desc"):
        found.extend(page)
        if len(found) >= limit:
            break
    return found[:limit]


def find_possible_duplicates(
    title: str,
    existing: Sequence[GithubIssue],
    embedder: Embedder | None,
    *,
    min_similarity: float,
    limit: int = DEFAULT_CANDIDATES,
) -> list[DuplicateCandidate]:
    """Rank existing issues by how close their title is to the draft's."""
    if not existing:
        return []

    if embedder is not None:
        vectors = unit_vectors(
            embedder.embed([title, *(issue.title for issue in existing)]).vectors
        )
        scores = (vectors[1:] @ vectors[0]).tolist()
    else:
        # No embedding model: fall back to shared words, which still catches near-copies.
        scores = [_word_overlap(title, issue.title) for issue in existing]

    candidates = [
        DuplicateCandidate(
            number=issue.number, title=issue.title, url=issue.url, similarity=round(score, 3)
        )
        for issue, score in zip(existing, scores, strict=True)
        if score >= min_similarity
    ]
    candidates.sort(key=lambda candidate: candidate.similarity, reverse=True)
    return candidates[:limit]


def _word_overlap(first: str, second: str) -> float:
    left, right = set(WORD.findall(first.lower())), set(WORD.findall(second.lower()))
    return len(left & right) / len(left | right) if left and right else 0.0
