"""Tests run against a separate `<database>_test` database, so local data is never touched."""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, make_url, text

from app.config import Settings

_base_url = make_url(Settings().database_url)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _base_url.set(
    database=f"{_base_url.database}_test"
).render_as_string(hide_password=False)
# Must happen before app.db is imported, because the engine is created at import time.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.auth.tokens import create_access_token, signing_secret  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FeedbackItem, Membership, Source, User, Workspace  # noqa: E402
from app.processing.hashing import content_hash  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "test-password"
# Hashing is deliberately slow, so the test user's hash is computed once for the whole run.
OWNER_PASSWORD_HASH = hash_password(OWNER_PASSWORD)


def _ensure_database_exists(url: str) -> None:
    target = make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    _ensure_database_exists(TEST_DATABASE_URL)
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


@pytest.fixture
def db() -> Iterator[Session]:
    """A session on an empty database."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with SessionLocal() as session:
        yield session


@pytest.fixture
def workspace(db: Session) -> Workspace:
    workspace = Workspace(slug="test", name="Test workspace")
    db.add(workspace)
    db.commit()
    return workspace


@pytest.fixture
def owner(db: Session, workspace: Workspace) -> User:
    """A signed-up person who owns the test workspace."""
    user = User(email=OWNER_EMAIL, name="Test Owner", password_hash=OWNER_PASSWORD_HASH)
    db.add(user)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()
    return user


@pytest.fixture
def auth_headers(owner: User) -> dict[str, str]:
    token = create_access_token(
        owner.id, secret=signing_secret(get_settings()), valid_for=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(auth_headers: dict[str, str]) -> Iterator[TestClient]:
    """A signed-in client. Tests that need an anonymous one build their own."""
    yield TestClient(app, headers=auth_headers)
    app.dependency_overrides.clear()


@pytest.fixture
def other_workspace(db: Session, owner: User) -> Workspace:
    """A second workspace the same person owns, for proving data stays in its own workspace."""
    workspace = Workspace(slug="other", name="Other workspace")
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=owner.id, role="owner"))
    db.commit()
    return workspace


@pytest.fixture
def source(db: Session, workspace: Workspace) -> Source:
    source = Source(
        workspace_id=workspace.id,
        kind="github",
        name="acme/app",
        config={"repo": "acme/app", "backfill_days": 7, "max_items": 100},
    )
    db.add(source)
    db.commit()
    return source


@pytest.fixture
def make_item(db: Session, source: Source) -> Callable[..., FeedbackItem]:
    """Insert a feedback item directly, as if it had been imported."""

    def make(
        number: int, *, maintainer: bool = False, body: str = "The editor freezes when saving."
    ) -> FeedbackItem:
        title = f"Issue {number}"
        created_at = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=number)
        item = FeedbackItem(
            workspace_id=source.workspace_id,
            source_id=source.id,
            external_id=str(number),
            url=f"https://github.com/acme/app/issues/{number}",
            title=title,
            body_raw=body,
            body_clean=body,
            content_hash=content_hash(title, body),
            author_hash=f"author-{number}",
            author_is_maintainer=maintainer,
            state="open",
            external_created_at=created_at,
            external_updated_at=created_at,
        )
        db.add(item)
        db.commit()
        return item

    return make
