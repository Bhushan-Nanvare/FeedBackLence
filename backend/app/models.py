from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SOURCE_KINDS = ("github", "csv", "widget")
JOB_STATUSES = ("queued", "running", "done", "failed")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Source(TimestampMixin, Base):
    """Where feedback comes from, e.g. one GitHub repository."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        CheckConstraint(_one_of("kind", SOURCE_KINDS), name="kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    # What to import (e.g. repo, backfill window) — set by the user.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Sync bookkeeping (e.g. cursor) — managed by the importer.
    state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeedbackItem(TimestampMixin, Base):
    """One piece of user feedback, e.g. a GitHub issue."""

    __tablename__ = "feedback_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index(
            "ix_feedback_items_workspace_id_external_created_at",
            "workspace_id",
            "external_created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body_raw: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Template text, logs and screenshots removed; this is what AI steps read.
    body_clean: Mapped[str] = mapped_column(Text, default="", server_default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    author_hash: Mapped[str] = mapped_column(String(64))
    author_is_maintainer: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    state: Mapped[str] = mapped_column(String(20))
    state_reason: Mapped[str | None] = mapped_column(String(30))
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    comments_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    reactions_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    external_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    external_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Job(TimestampMixin, Base):
    """A unit of background work, claimed by workers from this table (see app.jobs.queue)."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_one_of("status", JOB_STATUSES), name="status"),
        Index("ix_jobs_status_run_after", "status", "run_after"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), default="queued", server_default=text("'queued'")
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(default=5, server_default=text("5"))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
