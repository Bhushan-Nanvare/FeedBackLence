from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import EmbedderDep, SessionDep, WorkspaceDep
from app.api.schemas import FeedbackItemRead, SearchHitRead, SearchQuery, SearchResults
from app.search.hybrid import SearchFilters, hybrid_search, load_items

router = APIRouter(prefix="/workspaces/{slug}/search", tags=["search"])


@router.get("", response_model=SearchResults)
def search(
    query: Annotated[SearchQuery, Query()],
    workspace: WorkspaceDep,
    session: SessionDep,
    embedder: EmbedderDep,
) -> SearchResults:
    """Find feedback matching a question, by words and by meaning."""
    hits = hybrid_search(
        session,
        workspace.id,
        query.q,
        embedder,
        limit=query.limit,
        filters=SearchFilters(
            type=query.type,
            area=query.area,
            state=query.state,
            created_after=query.created_after,
            created_before=query.created_before,
            include_maintainer=query.include_maintainer,
        ),
    )
    items = {item.id: item for item in load_items(session, hits)}

    return SearchResults(
        question=query.q,
        searched_by_meaning=embedder is not None,
        hits=[
            SearchHitRead(
                item=FeedbackItemRead.model_validate(items[hit.item_id]),
                score=hit.score,
                matched_by=hit.matched_by,
            )
            for hit in hits
            if hit.item_id in items
        ],
    )
