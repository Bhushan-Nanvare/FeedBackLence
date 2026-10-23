from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import ManagedWorkspaceDep, SessionDep, UserDep
from app.api.schemas import MemberInvite, MemberRead, WorkspaceCreate, WorkspaceRead
from app.models import Membership, User, Workspace

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, user: UserDep, session: SessionDep) -> WorkspaceRead:
    """Make a workspace. Whoever creates it owns it."""
    workspace = Workspace(slug=body.slug, name=body.name, is_public=False)
    session.add(workspace)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{body.slug}' is taken") from None

    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.commit()
    return WorkspaceRead(
        slug=workspace.slug, name=workspace.name, is_public=workspace.is_public, role="owner"
    )


@router.get("/workspaces", response_model=list[WorkspaceRead])
def my_workspaces(user: UserDep, session: SessionDep) -> list[WorkspaceRead]:
    rows = session.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.slug)
    ).all()
    return [
        WorkspaceRead(
            slug=workspace.slug, name=workspace.name, is_public=workspace.is_public, role=role
        )
        for workspace, role in rows
    ]


@router.get("/workspaces/{slug}/members", response_model=list[MemberRead])
def list_members(workspace: ManagedWorkspaceDep, session: SessionDep) -> list[MemberRead]:
    rows = session.execute(
        select(Membership.role, User.email, User.name)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace.id)
        .order_by(User.email)
    ).all()
    return [MemberRead(email=email, name=name, role=role) for role, email, name in rows]


@router.post(
    "/workspaces/{slug}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    body: MemberInvite, workspace: ManagedWorkspaceDep, session: SessionDep
) -> MemberRead:
    """Give someone who already has an account access to this workspace."""
    invited = session.scalar(select(User).where(User.email == body.email.strip().lower()))
    if invited is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Nobody with that email address has registered yet"
        )

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace.id, Membership.user_id == invited.id
        )
    )
    if membership is None:
        membership = Membership(workspace_id=workspace.id, user_id=invited.id, role=body.role)
        session.add(membership)
    else:
        membership.role = body.role
    session.commit()
    return MemberRead(email=invited.email, name=invited.name, role=membership.role)


@router.delete(
    "/workspaces/{slug}/members/{email}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(email: str, workspace: ManagedWorkspaceDep, session: SessionDep) -> None:
    """Remove a member from the workspace. Owners cannot remove themselves."""
    target = session.scalar(select(User).where(User.email == email.strip().lower()))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace.id, Membership.user_id == target.id
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person is not a member")

    if membership.role == "owner":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Cannot remove the owner — transfer ownership first",
        )

    session.delete(membership)
    session.commit()
