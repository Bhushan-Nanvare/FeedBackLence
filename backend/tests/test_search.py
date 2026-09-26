from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.embeddings import EMBEDDING_DIMENSIONS, EmbeddingResult
from app.api.deps import get_optional_embedder
from app.main import app
from app.models import FeedbackItem, ItemEmbedding, ItemTag, Workspace
from app.search.hybrid import RRF_K, SearchFilters, fuse, hybrid_search, keyword_search

MakeItem = Callable[..., FeedbackItem]
WriteItem = Callable[..., FeedbackItem]


def axis_vector(axis: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[axis] = 1.0
    return vector


class FakeEmbedder:
    """Returns whichever vector the test wants the question to look like."""

    model = "fake-embedder"

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self.vector for _ in texts], model=self.model, input_tokens=0, latency_ms=0
        )


@pytest.fixture
def write_item(db: Session, make_item: MakeItem) -> WriteItem:
    """An item with the title, text, vector and tags a search test needs."""

    def write(
        number: int,
        *,
        title: str,
        body: str = "",
        vector: list[float] | None = None,
        maintainer: bool = False,
        state: str = "open",
        tag_type: str | None = None,
        created_at: datetime | None = None,
    ) -> FeedbackItem:
        item = make_item(number, maintainer=maintainer, body=body)
        item.title = title
        item.state = state
        if created_at is not None:
            item.external_created_at = created_at
        if vector is not None:
            db.add(
                ItemEmbedding(
                    item_id=item.id,
                    workspace_id=item.workspace_id,
                    embedding=vector,
                    model="fake-embedder",
                    content_hash=item.content_hash,
                )
            )
        if tag_type is not None:
            db.add(
                ItemTag(
                    item_id=item.id,
                    workspace_id=item.workspace_id,
                    type=tag_type,
                    area="editor",
                    sentiment="negative",
                    urgency="medium",
                    confidence=0.9,
                    summary="",
                    content_hash=item.content_hash,
                    model="fake-model",
                    prompt_version="tag-v1",
                )
            )
        db.commit()
        return item

    return write


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_optional_embedder] = lambda: FakeEmbedder(axis_vector(0))
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_word_search_prefers_titles_over_body_text(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    in_body = write_item(1, title="Something else", body="The terminal crashes on startup.")
    in_title = write_item(2, title="Terminal crashes when splitting")
    write_item(3, title="Chat panel is slow", body="Nothing to do with the topic.")

    found = keyword_search(db, workspace.id, "terminal crashes", limit=10)

    assert found == [in_title.id, in_body.id]


def test_word_search_understands_word_endings(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    item = write_item(1, title="The editor freezes when saving")

    assert keyword_search(db, workspace.id, "freeze", limit=10) == [item.id]
    assert keyword_search(db, workspace.id, "nothing relevant", limit=10) == []


def test_word_search_skips_maintainer_items_unless_asked(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    write_item(1, title="Terminal crashes on split", maintainer=True)

    assert keyword_search(db, workspace.id, "terminal", limit=10) == []
    included = keyword_search(
        db, workspace.id, "terminal", limit=10, filters=SearchFilters(include_maintainer=True)
    )
    assert len(included) == 1


def test_fusion_puts_items_both_searches_found_on_top() -> None:
    hits = fuse([10, 20], [20, 30])

    assert [hit.item_id for hit in hits] == [20, 10, 30]
    both = hits[0]
    assert (both.keyword_rank, both.vector_rank) == (2, 1)
    assert both.score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert both.matched_by == ["words", "meaning"]
    assert hits[1].matched_by == ["words"]


def test_search_by_meaning_finds_items_that_share_no_words(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    same_meaning = write_item(1, title="Panel disappears after restart", vector=axis_vector(0))
    write_item(2, title="Completely unrelated report", vector=axis_vector(200))

    hits = hybrid_search(
        db, workspace.id, "sidebar vanishes on reopen", FakeEmbedder(axis_vector(0))
    )

    assert [hit.item_id for hit in hits][0] == same_meaning.id
    assert hits[0].matched_by == ["meaning"]


def test_without_an_embedder_search_still_works_on_words(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    item = write_item(1, title="Terminal crashes when splitting", vector=axis_vector(0))

    hits = hybrid_search(db, workspace.id, "terminal crashes", None)

    assert [hit.item_id for hit in hits] == [item.id]
    assert hits[0].matched_by == ["words"]


def test_filters_narrow_the_search(
    db: Session, workspace: Workspace, write_item: WriteItem
) -> None:
    old = write_item(
        1,
        title="Terminal crashes on split",
        state="closed",
        tag_type="bug",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    recent = write_item(
        2,
        title="Terminal crashes after update",
        tag_type="feature_request",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    assert keyword_search(
        db, workspace.id, "terminal", limit=10, filters=SearchFilters(state="closed")
    ) == [old.id]
    assert keyword_search(
        db, workspace.id, "terminal", limit=10, filters=SearchFilters(type="feature_request")
    ) == [recent.id]
    assert keyword_search(
        db,
        workspace.id,
        "terminal",
        limit=10,
        filters=SearchFilters(created_after=datetime(2026, 6, 1, tzinfo=UTC)),
    ) == [recent.id]


def test_search_endpoint_returns_ranked_items(
    client: TestClient, workspace: Workspace, write_item: WriteItem
) -> None:
    both = write_item(1, title="Terminal crashes when splitting", vector=axis_vector(0))
    write_item(2, title="Unrelated thing", vector=axis_vector(200))

    body = client.get("/workspaces/test/search", params={"q": "terminal crashes"}).json()

    assert body["question"] == "terminal crashes"
    assert body["searched_by_meaning"] is True
    assert body["hits"][0]["item"]["id"] == both.id
    assert body["hits"][0]["matched_by"] == ["words", "meaning"]


def test_search_endpoint_validates_its_input(client: TestClient, workspace: Workspace) -> None:
    assert client.get("/workspaces/test/search").status_code == 422
    assert client.get("/workspaces/test/search", params={"q": ""}).status_code == 422
    assert client.get("/workspaces/test/search", params={"q": "x", "limit": 99}).status_code == 422
    assert client.get("/workspaces/nope/search", params={"q": "x"}).status_code == 404
