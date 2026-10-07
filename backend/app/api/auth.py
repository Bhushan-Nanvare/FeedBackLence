from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, UserDep
from app.api.schemas import SignIn, SignUp, TokenRead, UserRead, WorkspaceMembership
from app.auth.passwords import check_password, hash_password
from app.auth.tokens import create_access_token, signing_secret
from app.config import get_settings
from app.models import Membership, User, Workspace

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
def register(body: SignUp, session: SessionDep) -> TokenRead:
    user = User(
        email=body.email.strip().lower(),
        name=body.name.strip(),
        password_hash=hash_password(body.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That email address is already registered"
        ) from None
    return _token_for(user)


@router.post("/login", response_model=TokenRead)
def login(body: SignIn, session: SessionDep) -> TokenRead:
    user = session.scalar(select(User).where(User.email == body.email.strip().lower()))
    # The same answer either way, so this cannot be used to discover who has an account.
    if user is None or not check_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email address or password")
    return _token_for(user)


@router.get("/me", response_model=UserRead)
def me(user: UserDep, session: SessionDep) -> UserRead:
    memberships = session.execute(
        select(Membership.role, Workspace.slug, Workspace.name)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.slug)
    ).all()
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        workspaces=[
            WorkspaceMembership(slug=slug, name=name, role=role) for role, slug, name in memberships
        ],
    )


def _token_for(user: User) -> TokenRead:
    settings = get_settings()
    token = create_access_token(
        user.id,
        secret=signing_secret(settings),
        valid_for=timedelta(days=settings.auth_token_days),
    )
    return TokenRead(access_token=token, user_id=user.id, email=user.email, name=user.name)
