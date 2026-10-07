from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import check_password, hash_password
from app.main import app
from app.models import FeedbackItem, Membership, User, Workspace

MakeItem = Callable[..., FeedbackItem]
SIGN_UP = {"email": "ada@example.com", "name": "Ada", "password": "a-good-password"}


@pytest.fixture
def anonymous(db: Session) -> Iterator[TestClient]:
    """Nobody is signed in on this one."""
    yield TestClient(app)
    app.dependency_overrides.clear()


def sign_in_as(client: TestClient, workspace: Workspace, db: Session, role: str) -> TestClient:
    """Register a second person with the given role in the workspace."""
    token = client.post(
        "/auth/register",
        json={"email": f"{role}@example.com", "name": role.title(), "password": "a-good-password"},
    ).json()["access_token"]
    user = db.scalar(select(User).where(User.email == f"{role}@example.com"))
    assert user is not None
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role=role))
    db.commit()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_registering_then_asking_who_i_am(anonymous: TestClient, db: Session) -> None:
    registered = anonymous.post("/auth/register", json=SIGN_UP)

    assert registered.status_code == 201
    token = registered.json()["access_token"]
    me = anonymous.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"
    assert me.json()["workspaces"] == []


def test_the_password_itself_is_never_stored(anonymous: TestClient, db: Session) -> None:
    anonymous.post("/auth/register", json=SIGN_UP)

    stored = db.scalar(select(User.password_hash).where(User.email == "ada@example.com"))

    assert stored is not None
    assert "a-good-password" not in stored
    assert check_password("a-good-password", stored)
    assert not check_password("the-wrong-password", stored)


def test_hashing_the_same_password_twice_gives_different_hashes() -> None:
    first, second = hash_password("same-password"), hash_password("same-password")

    assert first != second
    assert check_password("same-password", first)
    assert check_password("same-password", second)


def test_an_email_can_only_be_registered_once(anonymous: TestClient) -> None:
    anonymous.post("/auth/register", json=SIGN_UP)

    assert anonymous.post("/auth/register", json=SIGN_UP).status_code == 409


def test_signing_in(anonymous: TestClient) -> None:
    anonymous.post("/auth/register", json=SIGN_UP)

    wrong = anonymous.post("/auth/login", json={"email": "ada@example.com", "password": "not-it"})
    right = anonymous.post(
        "/auth/login", json={"email": "ADA@example.com", "password": "a-good-password"}
    )

    assert wrong.status_code == 401
    # The address is not case sensitive.
    assert right.status_code == 200
    assert right.json()["email"] == "ada@example.com"


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "name": "Ada", "password": "a-good-password"},
        {"email": "ada@example.com", "name": "Ada", "password": "short"},
        {"email": "ada@example.com", "name": "", "password": "a-good-password"},
    ],
)
def test_bad_sign_ups_are_rejected(anonymous: TestClient, body: dict[str, str]) -> None:
    assert anonymous.post("/auth/register", json=body).status_code == 422


def test_a_public_workspace_can_be_read_by_anyone(
    anonymous: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    make_item(1)
    workspace.is_public = True
    db.commit()

    assert anonymous.get("/workspaces/test/items").status_code == 200
    assert anonymous.get("/workspaces/test/themes").status_code == 200


def test_a_private_workspace_asks_you_to_sign_in(
    anonymous: TestClient, workspace: Workspace
) -> None:
    response = anonymous.get("/workspaces/test/items")

    assert response.status_code == 401
    assert "Sign in" in response.json()["detail"]


def test_reading_is_not_the_same_as_changing(
    anonymous: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1)
    workspace.is_public = True
    db.commit()

    reading = anonymous.get("/workspaces/test/items")
    changing = anonymous.patch(f"/workspaces/test/items/{item.id}/tag", json={"type": "bug"})

    assert reading.status_code == 200
    assert changing.status_code == 401


def test_someone_outside_the_workspace_is_refused(
    anonymous: TestClient, workspace: Workspace
) -> None:
    outsider = anonymous.post(
        "/auth/register",
        json={"email": "stranger@example.com", "name": "Stranger", "password": "a-good-password"},
    ).json()["access_token"]

    response = anonymous.get(
        "/workspaces/test/items", headers={"Authorization": f"Bearer {outsider}"}
    )

    assert response.status_code == 403


def test_a_viewer_may_look_but_not_change(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1)
    viewer = sign_in_as(client, workspace, db, "viewer")

    assert viewer.get("/workspaces/test/items").status_code == 200
    assert (
        viewer.patch(f"/workspaces/test/items/{item.id}/tag", json={"type": "bug"}).status_code
        == 403
    )


def test_a_member_may_change_feedback_but_not_settings(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1)
    member = sign_in_as(client, workspace, db, "member")

    changing = member.patch(f"/workspaces/test/items/{item.id}/tag", json={"type": "bug"})
    settings = member.put("/workspaces/test/product-areas", json=[{"slug": "x", "name": "X"}])

    assert changing.status_code == 200
    assert settings.status_code == 403


def test_creating_a_workspace_makes_you_its_owner(client: TestClient) -> None:
    created = client.post("/workspaces", json={"slug": "acme", "name": "Acme"})

    assert created.status_code == 201
    assert created.json() == {"slug": "acme", "name": "Acme", "is_public": False, "role": "owner"}
    mine = client.get("/workspaces").json()
    assert {workspace["slug"] for workspace in mine} == {"test", "acme"}


def test_a_taken_slug_is_refused(client: TestClient) -> None:
    client.post("/workspaces", json={"slug": "acme", "name": "Acme"})

    assert client.post("/workspaces", json={"slug": "acme", "name": "Other"}).status_code == 409


def test_inviting_someone_gives_them_access(
    client: TestClient, anonymous: TestClient, db: Session, workspace: Workspace
) -> None:
    token = anonymous.post("/auth/register", json=SIGN_UP).json()["access_token"]
    invited = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert invited.get("/workspaces/test/items").status_code == 403

    added = client.post(
        "/workspaces/test/members", json={"email": "ada@example.com", "role": "member"}
    )

    assert added.status_code == 201
    assert added.json()["role"] == "member"
    assert invited.get("/workspaces/test/items").status_code == 200


def test_inviting_someone_who_has_not_registered(client: TestClient, workspace: Workspace) -> None:
    response = client.post(
        "/workspaces/test/members", json={"email": "nobody@example.com", "role": "member"}
    )

    assert response.status_code == 404


def test_only_owners_and_admins_see_the_member_list(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    member = sign_in_as(client, workspace, db, "member")

    assert client.get("/workspaces/test/members").status_code == 200
    assert member.get("/workspaces/test/members").status_code == 403
