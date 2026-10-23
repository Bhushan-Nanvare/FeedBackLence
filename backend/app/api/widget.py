"""Widget API endpoints.

Three endpoints:

1. ``POST /workspaces/{slug}/widget/submit`` — accepts feedback from the
   embeddable widget.  This is **unauthenticated** because external visitors
   need to be able to submit feedback without signing in.  It is accepted
   only by workspaces that turned the widget on, so nobody can push feedback
   into a private workspace by guessing its name.

2. ``GET /workspaces/{slug}/widget/embed`` — the snippet to paste, and whether
   the widget is currently on.  Owners and admins only: it decides whether
   strangers may write to the workspace.

3. ``POST /workspaces/{slug}/widget/enable`` — turns the widget on or off.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import ManagedWorkspaceDep, SessionDep
from app.api.schemas import WidgetEmbed, WidgetSubmission, WidgetSubmissionResult, WidgetToggle
from app.models import Workspace
from app.sources.widget import set_widget_enabled, submit_feedback, widget_is_on, widget_source

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

    # -- A workspace only receives widget feedback once someone turned the widget
    #    on. Same answer as an unknown workspace, so this cannot be used to
    #    discover which workspaces exist.
    source = widget_source(session, workspace)
    if not widget_is_on(source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    assert source is not None  # widget_is_on already proved this

    # -- Create the feedback item and queue AI processing.
    item = submit_feedback(
        session,
        workspace,
        source,
        text=body.text,
        email=body.email,
        name=body.name,
    )
    session.commit()

    return WidgetSubmissionResult(item_id=item.id)


@router.get("/embed", response_model=WidgetEmbed)
def widget_embed(
    workspace: ManagedWorkspaceDep,
    session: SessionDep,
    request: Request,
) -> WidgetEmbed:
    """Return the embed snippet for this workspace, and whether it is switched on.

    The snippet is a ``<script>`` tag that loads the widget JS file and
    configures it with the workspace slug and API URL.  Workspace admins
    paste this into their website's HTML.
    """
    return _embed(workspace, request, enabled=widget_is_on(widget_source(session, workspace)))


@router.post("/enable", response_model=WidgetEmbed)
def widget_enable(
    body: WidgetToggle,
    workspace: ManagedWorkspaceDep,
    session: SessionDep,
    request: Request,
) -> WidgetEmbed:
    """Turn public submissions on or off. Feedback already collected is kept either way."""
    set_widget_enabled(session, workspace, body.enabled)
    session.commit()
    return _embed(workspace, request, enabled=body.enabled)


def _embed(workspace: Workspace, request: Request, *, enabled: bool) -> WidgetEmbed:
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
        enabled=enabled,
    )
