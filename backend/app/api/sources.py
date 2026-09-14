from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import GithubSourceCreate, JobRead, SourceRead
from app.jobs import queue
from app.models import Job, Source
from app.sources.github_sync import GITHUB_SYNC_JOB

router = APIRouter(prefix="/workspaces/{slug}/sources", tags=["sources"])


@router.get("", response_model=list[SourceRead])
def list_sources(workspace: WorkspaceDep, session: SessionDep) -> list[Source]:
    return list(
        session.scalars(
            select(Source).where(Source.workspace_id == workspace.id).order_by(Source.id)
        )
    )


@router.post("/github", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_github_source(
    body: GithubSourceCreate, workspace: WorkspaceDep, session: SessionDep
) -> Source:
    source = Source(
        workspace_id=workspace.id, kind="github", name=body.repo, config=body.model_dump()
    )
    session.add(source)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{body.repo} is already a source in this workspace"
        ) from None
    return source


@router.post("/{source_id}/sync", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def sync_source(source_id: int, workspace: WorkspaceDep, session: SessionDep) -> Job:
    """Queue a sync for the worker. Returns the already-queued job if one is pending."""
    source = session.get(Source, source_id)
    if source is None or source.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    if source.kind != "github":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only GitHub sources sync")

    payload = {"source_id": source.id}
    job = queue.find_active(session, GITHUB_SYNC_JOB, payload) or queue.enqueue(
        session, GITHUB_SYNC_JOB, payload, workspace_id=workspace.id
    )
    session.commit()
    return job
