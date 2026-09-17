from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select

from app.ai.tagging import OTHER_AREA, PROMPT_VERSION
from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import (
    FeedbackItemDetail,
    FeedbackItemRead,
    ItemFilters,
    ItemPage,
    ItemTagRead,
    ItemTagUpdate,
)
from app.models import FeedbackItem, ItemTag, ProductArea, Workspace

router = APIRouter(prefix="/workspaces/{slug}/items", tags=["items"])

SORT_ORDERS = {
    "newest": (FeedbackItem.external_created_at.desc(), FeedbackItem.id.desc()),
    "oldest": (FeedbackItem.external_created_at.asc(), FeedbackItem.id.asc()),
    "most_reactions": (
        FeedbackItem.reactions_count.desc(),
        FeedbackItem.external_created_at.desc(),
    ),
}
# Characters that would otherwise act as wildcards in a LIKE pattern.
LIKE_ESCAPES = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


@router.get("", response_model=ItemPage)
def list_items(
    filters: Annotated[ItemFilters, Query()], workspace: WorkspaceDep, session: SessionDep
) -> ItemPage:
    query = _filtered_items(workspace.id, filters)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(*SORT_ORDERS[filters.sort]).limit(filters.limit).offset(filters.offset)
    ).all()
    return ItemPage(total=total, items=[FeedbackItemRead.model_validate(item) for item in items])


@router.get("/{item_id}", response_model=FeedbackItemDetail)
def get_item(item_id: int, workspace: WorkspaceDep, session: SessionDep) -> FeedbackItem:
    return _item_or_404(session, workspace, item_id)


@router.patch("/{item_id}/tag", response_model=ItemTagRead)
def correct_tag(
    item_id: int, changes: ItemTagUpdate, workspace: WorkspaceDep, session: SessionDep
) -> ItemTag:
    """Save a person's correction. Corrected tags are never overwritten by AI."""
    item = _item_or_404(session, workspace, item_id)
    if changes.area is not None and changes.area != OTHER_AREA:
        known_area = session.scalar(
            select(ProductArea.id).where(
                ProductArea.workspace_id == workspace.id, ProductArea.slug == changes.area
            )
        )
        if known_area is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown product area '{changes.area}'"
            )

    tag = item.tag
    if tag is None:
        tag = ItemTag(
            item_id=item.id,
            workspace_id=workspace.id,
            type="other",
            area=OTHER_AREA,
            sentiment="neutral",
            urgency="low",
            confidence=1.0,
            summary="",
            content_hash=item.content_hash,
            model="human",
            prompt_version=PROMPT_VERSION,
        )
        session.add(tag)

    for field, value in changes.model_dump(exclude_none=True).items():
        setattr(tag, field, value)
    tag.reviewed_by_human = True
    session.commit()
    return tag


def _filtered_items(workspace_id: int, filters: ItemFilters) -> Select[tuple[FeedbackItem]]:
    query = (
        select(FeedbackItem)
        .outerjoin(ItemTag, ItemTag.item_id == FeedbackItem.id)
        .where(FeedbackItem.workspace_id == workspace_id)
    )
    if not filters.include_maintainer:
        query = query.where(FeedbackItem.author_is_maintainer.is_(False))
    if filters.untagged:
        query = query.where(ItemTag.item_id.is_(None))
    if filters.type is not None:
        query = query.where(ItemTag.type == filters.type)
    if filters.area is not None:
        query = query.where(ItemTag.area == filters.area)
    if filters.sentiment is not None:
        query = query.where(ItemTag.sentiment == filters.sentiment)
    if filters.urgency is not None:
        query = query.where(ItemTag.urgency == filters.urgency)
    if filters.state is not None:
        query = query.where(FeedbackItem.state == filters.state)
    if filters.q:
        # Plain "contains" search for now; Phase 3 adds proper full-text search.
        pattern = f"%{filters.q.translate(LIKE_ESCAPES)}%"
        query = query.where(
            or_(
                FeedbackItem.title.ilike(pattern, escape="\\"),
                FeedbackItem.body_clean.ilike(pattern, escape="\\"),
            )
        )
    return query


def _item_or_404(session: SessionDep, workspace: Workspace, item_id: int) -> FeedbackItem:
    item = session.get(FeedbackItem, item_id)
    if item is None or item.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback item not found")
    return item
