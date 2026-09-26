import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder, get_shared_embedder
from app.ai.llm import LLMClient, get_llm_client
from app.db import get_session
from app.errors import PermanentJobError
from app.models import Workspace

logger = logging.getLogger(__name__)

SessionDep = Annotated[Session, Depends(get_session)]


def get_optional_embedder() -> Embedder | None:
    """Search still works on words alone when no embedding model is configured."""
    try:
        return get_shared_embedder()
    except PermanentJobError as exc:
        logger.warning("searching by words only: %s", exc)
        return None


EmbedderDep = Annotated[Embedder | None, Depends(get_optional_embedder)]


def get_llm() -> LLMClient:
    """The text model. Answering needs it, so a missing key is reported to the caller."""
    try:
        return get_llm_client()
    except PermanentJobError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None


LLMDep = Annotated[LLMClient, Depends(get_llm)]


def get_workspace(slug: str, session: SessionDep) -> Workspace:
    workspace = session.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
