import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder, get_shared_embedder
from app.ai.llm import LLMClient, get_llm_client
from app.auth.tokens import read_access_token, signing_secret
from app.config import get_settings
from app.db import get_session
from app.errors import PermanentJobError
from app.models import MANAGING_ROLES, WRITING_ROLES, Membership, User, Workspace
from app.sources.github_client import GithubClient

logger = logging.getLogger(__name__)

SessionDep = Annotated[Session, Depends(get_session)]

# auto_error off: a missing token means "not signed in", which public pages allow.
bearer_token = HTTPBearer(auto_error=False)
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_token)]


def get_current_user(credentials: BearerDep, session: SessionDep) -> User | None:
    if credentials is None:
        return None
    user_id = read_access_token(credentials.credentials, secret=signing_secret(get_settings()))
    return session.get(User, user_id) if user_id is not None else None


CurrentUserDep = Annotated[User | None, Depends(get_current_user)]


def require_user(user: CurrentUserDep) -> User:
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in first",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


UserDep = Annotated[User, Depends(require_user)]


def role_of(session: Session, workspace: Workspace, user: User | None) -> str | None:
    if user is None:
        return None
    return session.scalar(
        select(Membership.role).where(
            Membership.workspace_id == workspace.id, Membership.user_id == user.id
        )
    )


def readable_workspace(slug: str, session: SessionDep, user: CurrentUserDep) -> Workspace:
    """Anyone may read a public workspace; otherwise you must be a member."""
    workspace = workspace_or_404(session, slug)
    if workspace.is_public or role_of(session, workspace, user) is not None:
        return workspace
    raise _no_access(user, "see")


def writable_workspace(slug: str, session: SessionDep, user: CurrentUserDep) -> Workspace:
    """Changing feedback needs a member role, even in a public workspace."""
    workspace = workspace_or_404(session, slug)
    if role_of(session, workspace, user) in WRITING_ROLES:
        return workspace
    raise _no_access(user, "change")


def managed_workspace(slug: str, session: SessionDep, user: CurrentUserDep) -> Workspace:
    """Settings and people are for owners and admins."""
    workspace = workspace_or_404(session, slug)
    if role_of(session, workspace, user) in MANAGING_ROLES:
        return workspace
    raise _no_access(user, "manage")


ReadableWorkspaceDep = Annotated[Workspace, Depends(readable_workspace)]
WritableWorkspaceDep = Annotated[Workspace, Depends(writable_workspace)]
ManagedWorkspaceDep = Annotated[Workspace, Depends(managed_workspace)]


def workspace_or_404(session: Session, slug: str) -> Workspace:
    workspace = session.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


def _no_access(user: User | None, action: str) -> HTTPException:
    if user is None:
        return HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Sign in to {action} this workspace",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return HTTPException(status.HTTP_403_FORBIDDEN, f"You do not have access to {action} this")


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


def get_github_client() -> Iterator[GithubClient]:
    client = GithubClient(token=get_settings().github_token)
    try:
        yield client
    finally:
        client.close()


GithubClientDep = Annotated[GithubClient, Depends(get_github_client)]
