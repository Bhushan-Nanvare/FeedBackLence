"""Tests run against a separate `<database>_test` database, so local data is never touched."""

import os
from collections.abc import Iterator
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
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Workspace  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


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
