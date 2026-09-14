from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import JobRead
from app.models import Job

router = APIRouter(prefix="/workspaces/{slug}/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, workspace: WorkspaceDep, session: SessionDep) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job
