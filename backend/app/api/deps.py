from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Workspace

SessionDep = Annotated[Session, Depends(get_session)]


def get_workspace(slug: str, session: SessionDep) -> Workspace:
    workspace = session.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
