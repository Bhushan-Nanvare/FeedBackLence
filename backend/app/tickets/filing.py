"""Create ticket drafts and, once a person approves, file them as issues."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder
from app.config import Settings, get_settings
from app.errors import PermanentJobError
from app.models import Source, Theme, Ticket, Workspace
from app.sources.github_client import GithubClient
from app.tickets.draft import build_draft
from app.tickets.duplicates import fetch_recent_issues, find_possible_duplicates

logger = logging.getLogger(__name__)


def draft_ticket(
    session: Session,
    workspace: Workspace,
    theme: Theme,
    *,
    repo: str | None = None,
    client: GithubClient | None = None,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> Ticket:
    """Write (or rewrite) the draft for a theme, including any possible duplicates."""
    settings = settings or get_settings()
    target = repo or settings.ticket_repo
    if not target:
        raise PermanentJobError(
            "No repository to file into. Set TICKET_REPO in .env to a repository you own."
        )
    check_repo_allowed(session, workspace, target, settings)

    content = build_draft(session, theme)
    duplicates = []
    if client is not None:
        try:
            existing = fetch_recent_issues(
                client, target, limit=settings.ticket_duplicate_candidates
            )
        except Exception as exc:
            # Writing the draft is local work, so a failed lookup should not lose it.
            # A wrong repository name shows up clearly at filing time instead.
            logger.warning("could not read issues in %s for a duplicate check: %s", target, exc)
            existing = []
        duplicates = [
            candidate.as_dict()
            for candidate in find_possible_duplicates(
                content.title,
                existing,
                embedder,
                min_similarity=settings.ticket_duplicate_min_similarity,
            )
        ]

    ticket = session.scalar(
        select(Ticket).where(Ticket.theme_id == theme.id, Ticket.status == "draft")
    )
    if ticket is None:
        ticket = Ticket(workspace_id=workspace.id, theme_id=theme.id, repo=target)
        session.add(ticket)
    ticket.repo = target
    ticket.title = content.title
    ticket.body = content.body
    ticket.duplicate_candidates = duplicates
    session.commit()
    return ticket


def file_ticket(session: Session, ticket: Ticket, client: GithubClient) -> Ticket:
    """File an approved draft. Called only when a person asks for it."""
    if ticket.status == "filed":
        return ticket

    workspace = session.get(Workspace, ticket.workspace_id)
    if workspace is not None:
        check_repo_allowed(session, workspace, ticket.repo, get_settings())

    owner, name = ticket.repo.split("/", 1)
    try:
        created = client.create_issue(owner, name, title=ticket.title, body=ticket.body)
    except Exception as exc:
        ticket.status = "failed"
        ticket.error = str(exc)[:2000]
        session.commit()
        raise

    ticket.status = "filed"
    ticket.external_id = str(created.number)
    ticket.external_url = created.url
    ticket.error = None
    ticket.filed_at = datetime.now(UTC)
    session.commit()
    logger.info("filed ticket %s as %s", ticket.id, created.url)
    return ticket


def check_repo_allowed(
    session: Session, workspace: Workspace, repo: str, settings: Settings
) -> None:
    """Refuse to file into a repository this workspace only reads from."""
    if settings.allow_filing_to_source_repo:
        return
    imported_from = set(
        session.scalars(
            select(Source.name).where(Source.workspace_id == workspace.id, Source.kind == "github")
        )
    )
    if repo in imported_from:
        raise PermanentJobError(
            f"{repo} is a repository this workspace imports from, so filing there would post "
            "into someone else's project. Set TICKET_REPO to a repository you own."
        )
