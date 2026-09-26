"""Find the feedback most relevant to a question.

Two searches run side by side: one on words, one on meaning. Word search catches exact terms
like error codes; meaning search catches reports that use different words for the same
problem. Their rankings are merged with reciprocal rank fusion, which needs no way to compare
the two kinds of score against each other.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder
from app.models import FeedbackItem, ItemEmbedding, ItemTag

# From the reciprocal rank fusion paper: stops the top hit from dominating, so agreement
# between the two searches still counts further down the list.
RRF_K = 60
DEFAULT_CANDIDATES = 50
DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class SearchFilters:
    type: str | None = None
    area: str | None = None
    state: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    include_maintainer: bool = False


@dataclass(frozen=True)
class SearchHit:
    item_id: int
    score: float
    keyword_rank: int | None
    vector_rank: int | None

    @property
    def matched_by(self) -> list[str]:
        found = []
        if self.keyword_rank is not None:
            found.append("words")
        if self.vector_rank is not None:
            found.append("meaning")
        return found


def hybrid_search(
    session: Session,
    workspace_id: int,
    question: str,
    embedder: Embedder | None,
    *,
    limit: int = DEFAULT_LIMIT,
    candidates: int = DEFAULT_CANDIDATES,
    filters: SearchFilters | None = None,
) -> list[SearchHit]:
    """Rank feedback for a question. Without an embedder, word search is used alone."""
    filters = filters or SearchFilters()
    by_words = keyword_search(session, workspace_id, question, limit=candidates, filters=filters)
    by_meaning: list[int] = []
    if embedder is not None:
        question_vector = embedder.embed([question]).vectors[0]
        by_meaning = vector_search(
            session, workspace_id, question_vector, limit=candidates, filters=filters
        )
    return fuse(by_words, by_meaning)[:limit]


def keyword_search(
    session: Session,
    workspace_id: int,
    question: str,
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[int]:
    if not question.strip():
        return []
    # websearch_to_tsquery understands quotes and "or", and never fails on odd input.
    terms = func.websearch_to_tsquery("english", question)
    statement = (
        _base_query(workspace_id, filters or SearchFilters())
        .where(FeedbackItem.search_vector.op("@@")(terms))
        .order_by(func.ts_rank_cd(FeedbackItem.search_vector, terms).desc(), FeedbackItem.id)
        .limit(limit)
    )
    return list(session.scalars(statement))


def vector_search(
    session: Session,
    workspace_id: int,
    question_vector: Sequence[float],
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[int]:
    distance = ItemEmbedding.embedding.cosine_distance(list(question_vector))
    statement = (
        _base_query(workspace_id, filters or SearchFilters())
        .join(ItemEmbedding, ItemEmbedding.item_id == FeedbackItem.id)
        .order_by(distance, FeedbackItem.id)
        .limit(limit)
    )
    return list(session.scalars(statement))


def fuse(keyword_ids: Sequence[int], vector_ids: Sequence[int]) -> list[SearchHit]:
    """Merge two rankings, so items both searches agree on rise to the top."""
    keyword_ranks = {item_id: rank for rank, item_id in enumerate(keyword_ids, start=1)}
    vector_ranks = {item_id: rank for rank, item_id in enumerate(vector_ids, start=1)}

    hits = []
    for item_id in {*keyword_ranks, *vector_ranks}:
        keyword_rank = keyword_ranks.get(item_id)
        vector_rank = vector_ranks.get(item_id)
        score = sum(1 / (RRF_K + rank) for rank in (keyword_rank, vector_rank) if rank is not None)
        hits.append(SearchHit(item_id, score, keyword_rank, vector_rank))
    return sorted(hits, key=lambda hit: (-hit.score, hit.item_id))


def load_items(session: Session, hits: Sequence[SearchHit]) -> list[FeedbackItem]:
    """Fetch the items behind the hits, keeping the ranking order."""
    if not hits:
        return []
    found = {
        item.id: item
        for item in session.scalars(
            select(FeedbackItem).where(FeedbackItem.id.in_([hit.item_id for hit in hits]))
        )
    }
    return [found[hit.item_id] for hit in hits if hit.item_id in found]


def _base_query(workspace_id: int, filters: SearchFilters) -> Select[tuple[int]]:
    query = select(FeedbackItem.id).where(FeedbackItem.workspace_id == workspace_id)
    if not filters.include_maintainer:
        query = query.where(FeedbackItem.author_is_maintainer.is_(False))
    if filters.state is not None:
        query = query.where(FeedbackItem.state == filters.state)
    if filters.created_after is not None:
        query = query.where(FeedbackItem.external_created_at >= filters.created_after)
    if filters.created_before is not None:
        query = query.where(FeedbackItem.external_created_at <= filters.created_before)
    if filters.type is not None or filters.area is not None:
        query = query.join(ItemTag, ItemTag.item_id == FeedbackItem.id)
        if filters.type is not None:
            query = query.where(ItemTag.type == filters.type)
        if filters.area is not None:
            query = query.where(ItemTag.area == filters.area)
    return query
