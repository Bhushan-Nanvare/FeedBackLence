from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.alerts.detection import request_trend_check
from app.api.deps import ReadableWorkspaceDep, SessionDep, WritableWorkspaceDep
from app.api.schemas import AlertRead, JobRead
from app.models import Alert, Job, Theme

router = APIRouter(prefix="/workspaces/{slug}/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def list_alerts(
    workspace: ReadableWorkspaceDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AlertRead]:
    """Themes that grew unusually fast, newest first."""
    rows = session.execute(
        select(Alert, Theme.name)
        .join(Theme, Theme.id == Alert.theme_id)
        .where(Alert.workspace_id == workspace.id)
        .order_by(Alert.week_start.desc(), Alert.ratio.desc(), Alert.id.desc())
        .limit(limit)
    ).all()

    return [
        AlertRead(
            id=alert.id,
            theme_id=alert.theme_id,
            theme_name=theme_name,
            week_start=alert.week_start,
            item_count=alert.item_count,
            baseline=alert.baseline,
            ratio=alert.ratio,
            status=alert.status,
            channel=alert.channel,
            created_at=alert.created_at,
        )
        for alert, theme_name in rows
    ]


@router.post("/check", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def check_now(workspace: WritableWorkspaceDep, session: SessionDep) -> Job:
    """Look for rising themes now. Grouping runs queue this automatically."""
    job = request_trend_check(session, workspace.id)
    session.commit()
    return job
