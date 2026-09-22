"""Create and store the vector form of each item's text, in batches, as a background job."""

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder, get_embedder
from app.config import get_settings
from app.jobs import queue
from app.models import AiCall, FeedbackItem, ItemEmbedding, Job
from app.themes.clustering import request_clustering

logger = logging.getLogger(__name__)

EMBED_ITEMS_JOB = "embed_items"
FEATURE = "embedding"
MAX_TEXT_CHARS = 1500


@dataclass
class EmbeddingStats:
    embedded: int = 0
    failed_batches: int = 0
    more_pending: bool = False


def request_embedding(session: Session, workspace_id: int) -> Job:
    """Queue an embedding run, reusing one that hasn't started yet. The caller commits."""
    payload = {"workspace_id": workspace_id}
    existing = queue.find_active(session, EMBED_ITEMS_JOB, payload, statuses=("queued",))
    return existing or queue.enqueue(session, EMBED_ITEMS_JOB, payload, workspace_id=workspace_id)


def pending_items_query(workspace_id: int) -> Select[tuple[FeedbackItem]]:
    """Items with no vector yet, or whose text changed after the last one was made."""
    return (
        select(FeedbackItem)
        .outerjoin(ItemEmbedding, ItemEmbedding.item_id == FeedbackItem.id)
        .where(
            FeedbackItem.workspace_id == workspace_id,
            FeedbackItem.author_is_maintainer.is_(False),
            or_(
                ItemEmbedding.item_id.is_(None),
                ItemEmbedding.content_hash != FeedbackItem.content_hash,
            ),
        )
        .order_by(FeedbackItem.external_created_at.desc(), FeedbackItem.id)
    )


def embed_pending_items(
    session: Session, workspace_id: int, embedder: Embedder, *, batch_size: int, max_items: int
) -> EmbeddingStats:
    stats = EmbeddingStats()
    items = list(session.scalars(pending_items_query(workspace_id).limit(max_items)))
    for start in range(0, len(items), batch_size):
        _embed_batch(session, workspace_id, embedder, items[start : start + batch_size], stats)

    # Only ask for another run if this one made progress.
    stats.more_pending = len(items) == max_items and stats.embedded > 0
    return stats


def run_embed_items_job(session: Session, payload: dict[str, Any]) -> None:
    settings = get_settings()
    workspace_id = payload["workspace_id"]
    stats = embed_pending_items(
        session,
        workspace_id,
        get_embedder(settings),
        batch_size=settings.embedding_batch_size,
        max_items=settings.embedding_max_items_per_job,
    )
    logger.info("embedded workspace %s: %s", workspace_id, asdict(stats))
    if stats.more_pending:
        queue.enqueue(session, EMBED_ITEMS_JOB, payload, workspace_id=workspace_id)
        session.commit()
    elif stats.embedded:
        # New vectors change the picture, so the themes are worth rebuilding.
        request_clustering(session, workspace_id)
        session.commit()


def embedding_text(item: FeedbackItem) -> str:
    return f"{item.title}\n\n{item.body_clean[:MAX_TEXT_CHARS]}".strip()


def _embed_batch(
    session: Session,
    workspace_id: int,
    embedder: Embedder,
    batch: list[FeedbackItem],
    stats: EmbeddingStats,
) -> None:
    call = AiCall(
        workspace_id=workspace_id,
        feature=FEATURE,
        model=embedder.model,
        items_count=len(batch),
        succeeded=False,
    )
    session.add(call)
    started = time.monotonic()
    try:
        result = embedder.embed([embedding_text(item) for item in batch])
    except Exception as exc:
        # Record the failed call, then let the worker decide: postpone, retry or fail.
        call.error = str(exc)[:2000]
        call.latency_ms = round((time.monotonic() - started) * 1000)
        session.commit()
        raise

    call.model = result.model
    call.input_tokens = result.input_tokens
    call.latency_ms = result.latency_ms
    if len(result.vectors) != len(batch):
        call.error = f"asked for {len(batch)} vectors, got {len(result.vectors)}"
        session.commit()
        stats.failed_batches += 1
        return

    call.succeeded = True
    rows = [
        {
            "item_id": item.id,
            "workspace_id": workspace_id,
            "embedding": vector,
            "model": result.model,
            "content_hash": item.content_hash,
        }
        for item, vector in zip(batch, result.vectors, strict=True)
    ]
    statement = insert(ItemEmbedding).values(rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[ItemEmbedding.item_id],
            set_={
                "embedding": statement.excluded.embedding,
                "model": statement.excluded.model,
                "content_hash": statement.excluded.content_hash,
                "updated_at": func.now(),
            },
        )
    )
    stats.embedded += len(rows)
    session.commit()
