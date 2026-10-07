from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import (
    EmbedderDep,
    GithubClientDep,
    ReadableWorkspaceDep,
    SessionDep,
    WritableWorkspaceDep,
)
from app.api.schemas import TicketDraftRequest, TicketRead, TicketUpdate
from app.errors import PermanentJobError, RateLimitedError
from app.models import Theme, Ticket, Workspace
from app.tickets.filing import draft_ticket, file_ticket

router = APIRouter(prefix="/workspaces/{slug}", tags=["tickets"])


@router.post(
    "/themes/{theme_id}/ticket", response_model=TicketRead, status_code=status.HTTP_201_CREATED
)
def draft_for_theme(
    theme_id: int,
    body: TicketDraftRequest,
    workspace: WritableWorkspaceDep,
    session: SessionDep,
    embedder: EmbedderDep,
    github: GithubClientDep,
) -> Ticket:
    """Write a draft issue for a theme, with any existing issues that look like it.

    Nothing is filed here: this only prepares the text for a person to review.
    """
    theme = session.get(Theme, theme_id)
    if theme is None or theme.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Theme not found")

    try:
        return draft_ticket(
            session,
            workspace,
            theme,
            repo=body.repo,
            client=github if body.check_duplicates else None,
            embedder=embedder,
        )
    except PermanentJobError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(workspace: ReadableWorkspaceDep, session: SessionDep) -> list[Ticket]:
    return list(
        session.scalars(
            select(Ticket)
            .where(Ticket.workspace_id == workspace.id)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        )
    )


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int, changes: TicketUpdate, workspace: WritableWorkspaceDep, session: SessionDep
) -> Ticket:
    """Edit the draft before filing it, or drop it."""
    ticket = _ticket_or_404(session, workspace, ticket_id)
    if ticket.status == "filed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This ticket is already filed and cannot be changed"
        )
    for field, value in changes.model_dump(exclude_none=True).items():
        setattr(ticket, field, value)
    session.commit()
    return ticket


@router.post("/tickets/{ticket_id}/file", response_model=TicketRead)
def file_now(
    ticket_id: int, workspace: WritableWorkspaceDep, session: SessionDep, github: GithubClientDep
) -> Ticket:
    """File the draft as a real issue. This is the approval step, so it is never automatic."""
    ticket = _ticket_or_404(session, workspace, ticket_id)
    if ticket.status == "dismissed":
        raise HTTPException(status.HTTP_409_CONFLICT, "This ticket was dismissed")

    try:
        return file_ticket(session, ticket, github)
    except PermanentJobError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub rejected it: {exc}") from None


def _ticket_or_404(session: SessionDep, workspace: Workspace, ticket_id: int) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or ticket.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket
