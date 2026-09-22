from collections.abc import Callable, Sequence

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.embedding import embed_pending_items, embedding_text, request_embedding
from app.ai.embeddings import EMBEDDING_DIMENSIONS, EmbeddingResult, get_embedder
from app.ai.local_embedder import LocalEmbedder
from app.config import Settings
from app.errors import PermanentJobError
from app.models import AiCall, FeedbackItem, ItemEmbedding, Workspace

MakeItem = Callable[..., FeedbackItem]


def vector_for(text: str) -> list[float]:
    """A stand-in vector that still differs between texts."""
    return [float(len(text) % 7)] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


class FakeEmbedder:
    model = "fake-embedder"

    def __init__(self, vectors_per_call: int | None = None) -> None:
        self.vectors_per_call = vectors_per_call
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls.append(list(texts))
        vectors = [vector_for(text) for text in texts]
        if self.vectors_per_call is not None:
            vectors = vectors[: self.vectors_per_call]
        return EmbeddingResult(vectors=vectors, model=self.model, input_tokens=12, latency_ms=3)


def run(
    db: Session,
    workspace: Workspace,
    embedder: object,
    *,
    batch_size: int = 10,
    max_items: int = 100,
):
    return embed_pending_items(
        db, workspace.id, embedder, batch_size=batch_size, max_items=max_items
    )


def stored(db: Session) -> dict[int, ItemEmbedding]:
    db.expire_all()
    return {row.item_id: row for row in db.scalars(select(ItemEmbedding))}


def test_embeds_user_feedback_in_batches_and_records_calls(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    items = [make_item(number) for number in (1, 2, 3)]
    maintainer_item = make_item(4, maintainer=True)
    embedder = FakeEmbedder()

    stats = run(db, workspace, embedder, batch_size=2)

    assert stats.embedded == 3
    assert [len(call) for call in embedder.calls] == [2, 1]
    rows = stored(db)
    assert sorted(rows) == sorted(item.id for item in items)
    assert maintainer_item.id not in rows
    assert len(rows[items[0].id].embedding) == EMBEDDING_DIMENSIONS
    assert (rows[items[0].id].model, rows[items[0].id].content_hash) == (
        "fake-embedder",
        items[0].content_hash,
    )
    calls = db.scalars(select(AiCall)).all()
    assert [(call.feature, call.items_count, call.succeeded) for call in calls] == [
        ("embedding", 2, True),
        ("embedding", 1, True),
    ]


def test_sends_title_and_text_together(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1, body="The editor freezes when saving.")
    embedder = FakeEmbedder()

    run(db, workspace, embedder)

    assert embedder.calls[0] == [f"{item.title}\n\n{item.body_clean}"]
    assert embedding_text(item).startswith(item.title)


def test_only_new_or_changed_items_are_embedded_again(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    first, second = make_item(1), make_item(2)
    run(db, workspace, FakeEmbedder())

    unchanged = FakeEmbedder()
    run(db, workspace, unchanged)
    assert unchanged.calls == []

    db.execute(
        update(FeedbackItem).where(FeedbackItem.id == second.id).values(content_hash="edited")
    )
    db.commit()
    changed = FakeEmbedder()
    stats = run(db, workspace, changed)

    assert stats.embedded == 1
    assert len(changed.calls[0]) == 1
    assert stored(db)[second.id].content_hash == "edited"
    assert stored(db)[first.id].content_hash == first.content_hash


def test_short_batch_is_recorded_as_a_failure(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    make_item(1)
    make_item(2)

    stats = run(db, workspace, FakeEmbedder(vectors_per_call=1), batch_size=2)

    assert (stats.embedded, stats.failed_batches) == (0, 1)
    call = db.scalars(select(AiCall)).one()
    assert call.succeeded is False
    assert call.error is not None and "asked for 2 vectors" in call.error
    assert stored(db) == {}


def test_reports_more_pending_when_the_item_limit_is_reached(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    for number in (1, 2, 3):
        make_item(number)

    first = run(db, workspace, FakeEmbedder(), max_items=2)
    second = run(db, workspace, FakeEmbedder(), max_items=2)

    assert (first.embedded, first.more_pending) == (2, True)
    assert (second.embedded, second.more_pending) == (1, False)


def test_request_embedding_reuses_a_job_that_has_not_started(
    db: Session, workspace: Workspace
) -> None:
    first = request_embedding(db, workspace.id)
    db.commit()

    assert request_embedding(db, workspace.id).id == first.id


def test_local_embedder_rejects_the_wrong_vector_size() -> None:
    class WrongSize:
        def embed(self, texts: list[str]):
            import numpy

            return [numpy.zeros(10) for _ in texts]

    embedder = LocalEmbedder("tiny-model", embedder=WrongSize())

    with pytest.raises(PermanentJobError, match="10 numbers"):
        embedder.embed(["hello"])


def test_gemini_embeddings_need_a_key() -> None:
    with pytest.raises(PermanentJobError, match="GEMINI_API_KEY"):
        get_embedder(Settings(embedding_provider="gemini", gemini_api_key=None))
