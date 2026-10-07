import hashlib
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import EMBEDDING_DIMENSIONS, EmbeddingResult
from app.api.deps import get_github_client, get_optional_embedder
from app.config import Settings
from app.errors import PermanentJobError
from app.main import app
from app.models import FeedbackItem, Source, Theme, ThemeItem, ThemeWeeklyStat, Ticket, Workspace
from app.sources.github_client import CreatedIssue, GithubIssue
from app.tickets.draft import build_draft
from app.tickets.duplicates import find_possible_duplicates
from app.tickets.filing import draft_ticket, file_ticket

MakeItem = Callable[..., FeedbackItem]
OUR_REPO = "my-name/my-repo"
SETTINGS = Settings(ticket_repo=OUR_REPO)


def title_vector(text: str) -> list[float]:
    """Same text gives the same vector, different text an unrelated one."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    digest = int(hashlib.sha1(text.encode()).hexdigest(), 16)
    vector[digest % EMBEDDING_DIMENSIONS] = 1.0
    return vector


class FakeEmbedder:
    model = "fake-embedder"

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[title_vector(text) for text in texts],
            model=self.model,
            input_tokens=0,
            latency_ms=0,
        )


class FakeGithub:
    def __init__(
        self,
        existing: list[GithubIssue] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.existing = existing or []
        self.fail = fail
        self.created = CreatedIssue(number=42, url=f"https://github.com/{OUR_REPO}/issues/42")
        self.calls: list[tuple[str, Any]] = []

    def iter_issue_pages(
        self, owner: str, repo: str, *, sort: str, direction: str, since: Any = None
    ) -> Iterator[list[GithubIssue]]:
        self.calls.append(("list", f"{owner}/{repo}"))
        yield self.existing

    def create_issue(self, owner: str, repo: str, *, title: str, body: str) -> CreatedIssue:
        self.calls.append(("create", f"{owner}/{repo}", title))
        if self.fail is not None:
            raise self.fail
        return self.created


def existing_issue(number: int, title: str) -> GithubIssue:
    moment = datetime(2026, 9, 1, tzinfo=UTC)
    return GithubIssue(
        number=number,
        url=f"https://github.com/{OUR_REPO}/issues/{number}",
        title=title,
        body="",
        author_login="someone",
        author_is_maintainer=False,
        state="open",
        state_reason=None,
        labels=[],
        comments_count=0,
        reactions_count=0,
        created_at=moment,
        updated_at=moment,
    )


@pytest.fixture
def theme(db: Session, workspace: Workspace, make_item: MakeItem) -> Theme:
    theme = Theme(
        workspace_id=workspace.id,
        name="Terminal crashes when splitting a pane",
        centroid=[0.0] * EMBEDDING_DIMENSIONS,
        item_count=3,
        first_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 20, tzinfo=UTC),
        name_model="medoid",
    )
    db.add(theme)
    db.flush()
    for number in range(3):
        item = make_item(number, body=f"The terminal dies when I split pane {number}.")
        db.add(
            ThemeItem(
                item_id=item.id,
                theme_id=theme.id,
                workspace_id=workspace.id,
                similarity=0.9 - number / 100,
            )
        )
    for offset, count in enumerate([1, 1, 1, 1, 6]):
        db.add(
            ThemeWeeklyStat(
                theme_id=theme.id,
                week_start=(datetime(2026, 9, 21, tzinfo=UTC) - timedelta(weeks=4 - offset)).date(),
                item_count=count,
            )
        )
    db.commit()
    return theme


@pytest.fixture
def client(client: TestClient) -> Iterator[TestClient]:
    app.dependency_overrides[get_optional_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_github_client] = lambda: FakeGithub()
    yield client
    app.dependency_overrides.clear()


def test_draft_text_shows_the_numbers_and_real_examples(db: Session, theme: Theme) -> None:
    content = build_draft(db, theme)

    assert content.title == "Terminal crashes when splitting a pane"
    assert "**3 reports**" in content.body
    assert "First seen 2026-09-01, latest 2026-09-20." in content.body
    assert "6.0x the usual weekly rate" in content.body
    assert "### What people report" in content.body
    assert "https://github.com/acme/app/issues/0" in content.body
    assert "> The terminal dies when I split pane 0." in content.body
    assert "Grouped by FeedbackLens from acme/app." in content.body


def test_duplicate_check_finds_an_issue_about_the_same_thing() -> None:
    same = existing_issue(7, "Terminal crashes when splitting a pane")
    different = existing_issue(8, "Settings page will not open")

    found = find_possible_duplicates(
        "Terminal crashes when splitting a pane",
        [same, different],
        FakeEmbedder(),
        min_similarity=0.8,
    )

    assert [candidate.number for candidate in found] == [7]
    assert found[0].similarity == pytest.approx(1.0)


def test_duplicate_check_without_an_embedding_model_uses_shared_words() -> None:
    found = find_possible_duplicates(
        "Terminal crashes when splitting a pane",
        [
            existing_issue(7, "Terminal crashes when splitting a pane"),
            existing_issue(8, "Nothing alike"),
        ],
        None,
        min_similarity=0.9,
    )

    assert [candidate.number for candidate in found] == [7]


def test_drafting_twice_updates_the_same_draft(
    db: Session, workspace: Workspace, theme: Theme
) -> None:
    github = FakeGithub([existing_issue(7, "Terminal crashes when splitting a pane")])

    first = draft_ticket(
        db, workspace, theme, client=github, embedder=FakeEmbedder(), settings=SETTINGS
    )
    first_id = first.id
    assert first.duplicate_candidates[0]["number"] == 7

    theme.name = "Terminal dies on split"
    db.commit()
    second = draft_ticket(
        db, workspace, theme, client=github, embedder=FakeEmbedder(), settings=SETTINGS
    )

    assert second.id == first_id
    assert second.title == "Terminal dies on split"
    assert db.scalars(select(Ticket)).all() == [second]
    # The new title is nothing like the existing issue, so it is no longer flagged.
    assert second.duplicate_candidates == []


def test_a_failed_duplicate_check_still_produces_the_draft(
    db: Session, workspace: Workspace, theme: Theme
) -> None:
    class Unreachable:
        def iter_issue_pages(self, *args: Any, **kwargs: Any) -> Iterator[list[GithubIssue]]:
            raise RuntimeError("404 repository not found")
            yield []  # pragma: no cover - never reached, keeps this a generator

    ticket = draft_ticket(
        db, workspace, theme, client=Unreachable(), embedder=FakeEmbedder(), settings=SETTINGS
    )

    assert ticket.status == "draft"
    assert "**3 reports**" in ticket.body
    assert ticket.duplicate_candidates == []


def test_refuses_to_file_into_a_repository_we_only_read_from(
    db: Session, workspace: Workspace, theme: Theme, source: Source
) -> None:
    with pytest.raises(PermanentJobError, match="imports from"):
        draft_ticket(db, workspace, theme, repo=source.name, settings=SETTINGS)


def test_refuses_when_no_repository_is_configured(
    db: Session, workspace: Workspace, theme: Theme
) -> None:
    with pytest.raises(PermanentJobError, match="TICKET_REPO"):
        draft_ticket(db, workspace, theme, settings=Settings(ticket_repo=None))


def test_filing_saves_the_issue_link(db: Session, workspace: Workspace, theme: Theme) -> None:
    ticket = draft_ticket(db, workspace, theme, settings=SETTINGS)
    github = FakeGithub()

    filed = file_ticket(db, ticket, github)

    assert (filed.status, filed.external_id) == ("filed", "42")
    assert filed.external_url == f"https://github.com/{OUR_REPO}/issues/42"
    assert filed.filed_at is not None
    assert [call[0] for call in github.calls] == ["create"]

    # Filing again changes nothing and does not post a second issue.
    file_ticket(db, filed, github)
    assert [call[0] for call in github.calls] == ["create"]


def test_a_rejected_ticket_keeps_the_reason(
    db: Session, workspace: Workspace, theme: Theme
) -> None:
    ticket = draft_ticket(db, workspace, theme, settings=SETTINGS)

    with pytest.raises(PermanentJobError):
        file_ticket(db, ticket, FakeGithub(fail=PermanentJobError("GitHub refused the request")))

    db.expire_all()
    stored = db.get(Ticket, ticket.id)
    assert stored is not None
    assert (stored.status, stored.external_url) == ("failed", None)
    assert stored.error is not None and "refused" in stored.error


def test_draft_endpoint_returns_the_text_and_duplicates(
    client: TestClient, workspace: Workspace, theme: Theme
) -> None:
    response = client.post(f"/workspaces/test/themes/{theme.id}/ticket", json={"repo": OUR_REPO})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["repo"] == OUR_REPO
    assert "**3 reports**" in body["body"]
    assert body["duplicate_candidates"] == []


def test_draft_endpoint_refuses_a_repository_we_import_from(
    client: TestClient, workspace: Workspace, theme: Theme, source: Source
) -> None:
    response = client.post(f"/workspaces/test/themes/{theme.id}/ticket", json={"repo": source.name})

    assert response.status_code == 422
    assert "imports from" in response.json()["detail"]


def test_editing_then_filing_a_draft(
    client: TestClient, db: Session, workspace: Workspace, theme: Theme
) -> None:
    ticket_id = client.post(
        f"/workspaces/test/themes/{theme.id}/ticket", json={"repo": OUR_REPO}
    ).json()["id"]

    edited = client.patch(
        f"/workspaces/test/tickets/{ticket_id}", json={"title": "Splitting the terminal crashes it"}
    )
    filed = client.post(f"/workspaces/test/tickets/{ticket_id}/file")

    assert edited.json()["title"] == "Splitting the terminal crashes it"
    assert filed.status_code == 200
    assert filed.json()["status"] == "filed"
    assert filed.json()["external_url"].endswith("/issues/42")


def test_a_dismissed_draft_is_not_filed(
    client: TestClient, workspace: Workspace, theme: Theme
) -> None:
    ticket_id = client.post(
        f"/workspaces/test/themes/{theme.id}/ticket", json={"repo": OUR_REPO}
    ).json()["id"]
    client.patch(f"/workspaces/test/tickets/{ticket_id}", json={"status": "dismissed"})

    assert client.post(f"/workspaces/test/tickets/{ticket_id}/file").status_code == 409


def test_tickets_are_workspace_scoped(
    client: TestClient, workspace: Workspace, other_workspace: Workspace, theme: Theme
) -> None:
    ticket_id = client.post(
        f"/workspaces/test/themes/{theme.id}/ticket", json={"repo": OUR_REPO}
    ).json()["id"]

    assert client.post(f"/workspaces/other/tickets/{ticket_id}/file").status_code == 404
    assert client.get("/workspaces/other/tickets").json() == []
