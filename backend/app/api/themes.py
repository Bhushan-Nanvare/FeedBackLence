from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ReadableWorkspaceDep, SessionDep, WritableWorkspaceDep
from app.api.schemas import (
    FeedbackItemRead,
    JobRead,
    ThemeDetail,
    ThemeList,
    ThemeRead,
    ThemeUpdate,
    ThemeWeekRead,
)
from app.models import FeedbackItem, Job, Theme, ThemeItem, ThemeWeeklyStat, Workspace
from app.themes.clustering import request_clustering
from app.themes.trends import RECENT_WEEKS, WeekCount, fill_missing_weeks, growth_ratio

router = APIRouter(prefix="/workspaces/{slug}/themes", tags=["themes"])

ITEMS_IN_DETAIL = 20


@router.post("/recluster", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def recluster(workspace: WritableWorkspaceDep, session: SessionDep) -> Job:
    """Rebuild the themes from scratch. Imports queue this automatically."""
    job = request_clustering(session, workspace.id)
    session.commit()
    return job


@router.get("", response_model=ThemeList)
def list_themes(
    workspace: ReadableWorkspaceDep,
    session: SessionDep,
    status_filter: Literal["open", "ignored"] | None = Query(default=None, alias="status"),
    sort: Literal["size", "growth", "recent"] = "size",
    limit: int = Query(default=50, ge=1, le=200),
) -> ThemeList:
    query = select(Theme).where(Theme.workspace_id == workspace.id, Theme.item_count > 0)
    if status_filter is not None:
        query = query.where(Theme.status == status_filter)

    themes = list(session.scalars(query))
    weeks_by_theme = _weeks_by_theme(session, [theme.id for theme in themes])
    read = [_to_read(theme, weeks_by_theme.get(theme.id, [])) for theme in themes]
    read.sort(key=_sort_key(sort), reverse=True)
    return ThemeList(total=len(read), themes=read[:limit])


@router.get("/{theme_id}", response_model=ThemeDetail)
def get_theme(theme_id: int, workspace: ReadableWorkspaceDep, session: SessionDep) -> ThemeDetail:
    theme = _theme_or_404(session, workspace, theme_id)
    weeks = _weeks_by_theme(session, [theme.id]).get(theme.id, [])
    items = session.scalars(
        select(FeedbackItem)
        .join(ThemeItem, ThemeItem.item_id == FeedbackItem.id)
        .where(ThemeItem.theme_id == theme.id)
        .order_by(ThemeItem.similarity.desc())
        .limit(ITEMS_IN_DETAIL)
    ).all()

    return ThemeDetail(
        **_to_read(theme, weeks).model_dump(),
        items=[FeedbackItemRead.model_validate(item) for item in items],
    )


@router.patch("/{theme_id}", response_model=ThemeRead)
def update_theme(
    theme_id: int, changes: ThemeUpdate, workspace: WritableWorkspaceDep, session: SessionDep
) -> ThemeRead:
    """Rename a theme or hide it. A renamed theme keeps its name through later runs."""
    theme = _theme_or_404(session, workspace, theme_id)
    if changes.name is not None:
        theme.name = changes.name
        theme.renamed_by_human = True
        theme.name_model = "human"
    if changes.status is not None:
        theme.status = changes.status
    session.commit()
    return _to_read(theme, _weeks_by_theme(session, [theme.id]).get(theme.id, []))


def _theme_or_404(session: SessionDep, workspace: Workspace, theme_id: int) -> Theme:
    theme = session.get(Theme, theme_id)
    if theme is None or theme.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Theme not found")
    return theme


def _weeks_by_theme(session: SessionDep, theme_ids: list[int]) -> dict[int, list[WeekCount]]:
    if not theme_ids:
        return {}
    weeks: dict[int, list[WeekCount]] = {}
    for stat in session.scalars(
        select(ThemeWeeklyStat)
        .where(ThemeWeeklyStat.theme_id.in_(theme_ids))
        .order_by(ThemeWeeklyStat.week_start)
    ):
        weeks.setdefault(stat.theme_id, []).append(WeekCount(stat.week_start, stat.item_count))
    return weeks


def _to_read(theme: Theme, weeks: list[WeekCount]) -> ThemeRead:
    series = fill_missing_weeks(weeks, weeks=RECENT_WEEKS)
    return ThemeRead(
        id=theme.id,
        name=theme.name,
        summary=theme.summary,
        status=theme.status,
        item_count=theme.item_count,
        first_seen_at=theme.first_seen_at,
        last_seen_at=theme.last_seen_at,
        renamed_by_human=theme.renamed_by_human,
        weeks=[
            ThemeWeekRead(week_start=week.week_start, item_count=week.item_count) for week in series
        ],
        last_week_count=series[-1].item_count if series else 0,
        growth=growth_ratio(weeks),
    )


OLDEST = datetime.min.replace(tzinfo=UTC)


def _sort_key(sort: str) -> Callable[[ThemeRead], Any]:
    if sort == "growth":
        return lambda theme: (theme.growth or 0, theme.item_count)
    if sort == "recent":
        return lambda theme: (theme.last_seen_at or OLDEST, theme.item_count)
    return lambda theme: (theme.item_count, theme.last_week_count)
