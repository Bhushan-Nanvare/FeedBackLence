from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import CsvImportResult, GithubSourceCreate, JobRead, SourceRead
from app.jobs import queue
from app.models import Job, Source
from app.sources.csv_import import import_csv
from app.sources.github_sync import GITHUB_SYNC_JOB

router = APIRouter(prefix="/workspaces/{slug}/sources", tags=["sources"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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


@router.post("/csv", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
def import_csv_file(
    workspace: WorkspaceDep,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="A CSV export of feedback")],
) -> CsvImportResult:
    """Read feedback from a spreadsheet export. Emails and phone numbers are removed."""
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That file is larger than 5 MB."
        )
    if not raw.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That file is empty.")

    source, stats = import_csv(
        session,
        workspace,
        filename=file.filename or "upload.csv",
        content=raw.decode("utf-8-sig", errors="replace"),
    )
    return CsvImportResult(
        source=SourceRead.model_validate(source),
        created=stats.created,
        updated=stats.updated,
        unchanged=stats.unchanged,
        skipped=stats.skipped,
        problems=stats.problems,
    )


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
