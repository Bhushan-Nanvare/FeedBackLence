from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Select, delete, func, select

from app.ai.tagging import pending_items_query, request_tagging
from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import JobRead, ProductAreaIn, ProductAreaRead, TaggingStatus
from app.models import FeedbackItem, ItemTag, Job, ProductArea

router = APIRouter(prefix="/workspaces/{slug}", tags=["tagging"])


@router.get("/product-areas", response_model=list[ProductAreaRead])
def list_product_areas(workspace: WorkspaceDep, session: SessionDep) -> list[ProductArea]:
    return list(
        session.scalars(
            select(ProductArea)
            .where(ProductArea.workspace_id == workspace.id)
            .order_by(ProductArea.slug)
        )
    )


@router.put("/product-areas", response_model=list[ProductAreaRead])
def replace_product_areas(
    areas: list[ProductAreaIn], workspace: WorkspaceDep, session: SessionDep
) -> list[ProductArea]:
    """Replace the workspace's product areas. Existing tags keep their area until re-tagged."""
    slugs = [area.slug for area in areas]
    if len(set(slugs)) != len(slugs):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Product area slugs must be unique"
        )

    session.execute(delete(ProductArea).where(ProductArea.workspace_id == workspace.id))
    session.add_all([ProductArea(workspace_id=workspace.id, **area.model_dump()) for area in areas])
    session.commit()
    return list_product_areas(workspace, session)


@router.post("/tagging/run", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def run_tagging(workspace: WorkspaceDep, session: SessionDep) -> Job:
    """Queue tagging for untagged or changed items. Syncs also queue this automatically."""
    job = request_tagging(session, workspace.id)
    session.commit()
    return job


@router.get("/tagging/status", response_model=TaggingStatus)
def tagging_status(workspace: WorkspaceDep, session: SessionDep) -> TaggingStatus:
    def count(query: Select) -> int:
        return session.scalar(select(func.count()).select_from(query.subquery())) or 0

    items = select(FeedbackItem.id).where(FeedbackItem.workspace_id == workspace.id)
    tags = select(ItemTag.item_id).where(ItemTag.workspace_id == workspace.id)
    by_type = session.execute(
        select(ItemTag.type, func.count())
        .where(ItemTag.workspace_id == workspace.id)
        .group_by(ItemTag.type)
    ).tuples()

    return TaggingStatus(
        total_items=count(items),
        maintainer_items=count(items.where(FeedbackItem.author_is_maintainer.is_(True))),
        tagged_items=count(tags),
        reviewed_by_human=count(tags.where(ItemTag.reviewed_by_human.is_(True))),
        pending_items=count(pending_items_query(workspace.id).order_by(None)),
        by_type=dict(by_type.all()),
    )
