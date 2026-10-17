"""Widget API endpoints.

Two endpoints:

1. ``POST /workspaces/{slug}/widget/submit`` — accepts feedback from the
   embeddable widget.  This is **unauthenticated** because external visitors
   need to be able to submit feedback without signing in.  Only workspaces
   that exist receive submissions (404 otherwise).

2. ``GET /workspaces/{slug}/widget/embed`` — returns the embed snippet and
   configuration.  This is a read endpoint so ``ReadableWorkspaceDep`` is
   enough (any member or public reader can see the snippet).
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import ReadableWorkspaceDep, SessionDep
from app.api.schemas import WidgetEmbed, WidgetSubmission, WidgetSubmissionResult
from app.models import Workspace
from app.sources.widget import submit_feedback

router = APIRouter(prefix="/workspaces/{slug}/widget", tags=["widget"])


@router.post("/submit", response_model=WidgetSubmissionResult, status_code=status.HTTP_201_CREATED)
def widget_submit(
    slug: str,
    body: WidgetSubmission,
    session: SessionDep,
) -> WidgetSubmissionResult:
    """Accept one piece of feedback from the embeddable widget.

    This endpoint is intentionally unauthenticated — the widget is meant to
    be embedded on external websites where visitors do not have accounts.
    We do not use ReadableWorkspaceDep here because that requires the bearer
    token middleware to run; instead we look up the workspace directly.

    PII (emails, phone numbers) is scrubbed before anything is stored.
    Tagging and embedding jobs are queued automatically.
    """
    # -- Look up the workspace by slug.  We do this manually instead of using
    #    a dependency because widget submissions must work without any auth.
    workspace = session.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")

    # -- Create the feedback item and queue AI processing.
    item = submit_feedback(
        session,
        workspace,
        text=body.text,
        email=body.email,
        name=body.name,
    )
    session.commit()

    return WidgetSubmissionResult(item_id=item.id)


@router.get("/embed", response_model=WidgetEmbed)
def widget_embed(
    workspace: ReadableWorkspaceDep,
    request: Request,
) -> WidgetEmbed:
    """Return the embed snippet for this workspace.

    The snippet is a ``<script>`` tag that loads the widget JS file and
    configures it with the workspace slug and API URL.  Workspace admins
    paste this into their website's HTML.
    """
    # -- Build the API base URL from the current request so it works in both
    #    local development (http://localhost:8000) and production.
    api_url = str(request.base_url).rstrip("/")
    script_url = f"{api_url}/static/widget.js"

    # -- The snippet is a self-contained <script> tag that the workspace admin
    #    pastes into their site.  The data attributes configure the widget.
    snippet = (
        f'<script src="{script_url}" '
        f'data-workspace="{workspace.slug}" '
        f'data-api="{api_url}" '
        f"async></script>"
    )

    return WidgetEmbed(
        script_url=script_url,
        workspace_slug=workspace.slug,
        api_url=api_url,
        snippet=snippet,
    )
