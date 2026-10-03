from datetime import date, datetime
from typing import Any, Literal, get_args

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.db import Base

SOURCE_KINDS = ("github", "csv", "widget")
JOB_STATUSES = ("queued", "running", "done", "failed")
EVAL_LABEL_SOURCES = ("github_label", "human")
THEME_STATUSES = ("open", "ignored")
ALERT_STATUSES = ("pending", "sent", "failed", "skipped")
TICKET_STATUSES = ("draft", "filed", "dismissed", "failed")

TagType = Literal["bug", "feature_request", "question", "praise", "other"]
Sentiment = Literal["negative", "neutral", "positive"]
Urgency = Literal["low", "medium", "high"]
TAG_TYPES: tuple[str, ...] = get_args(TagType)
SENTIMENTS: tuple[str, ...] = get_args(Sentiment)
URGENCIES: tuple[str, ...] = get_args(Urgency)


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
        Index("ix_feedback_items_search_vector", "search_vector", postgresql_using="gin"),
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
    # Kept up to date by Postgres. Title words count for more than body words.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', title), 'A') || "
            "setweight(to_tsvector('english', body_clean), 'B')",
            persisted=True,
        ),
    )
    tag: Mapped["ItemTag | None"] = relationship(
        back_populates="item", lazy="selectin", cascade="all, delete-orphan"
    )


class ProductArea(TimestampMixin, Base):
    """A part of the product that feedback can be about, e.g. "terminal"."""

    __tablename__ = "product_areas"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")


class ItemTag(TimestampMixin, Base):
    """Labels for one feedback item, set by AI or corrected by a person."""

    __tablename__ = "item_tags"
    __table_args__ = (
        CheckConstraint(_one_of("type", TAG_TYPES), name="type"),
        CheckConstraint(_one_of("sentiment", SENTIMENTS), name="sentiment"),
        CheckConstraint(_one_of("urgency", URGENCIES), name="urgency"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        Index("ix_item_tags_workspace_id_type", "workspace_id", "type"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_items.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))
    # A product area slug, or "other".
    area: Mapped[str] = mapped_column(String(64))
    sentiment: Mapped[str] = mapped_column(String(10))
    urgency: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    # The item's content_hash when it was tagged; a mismatch means the text changed since.
    content_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    reviewed_by_human: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    item: Mapped["FeedbackItem"] = relationship(back_populates="tag")


class ItemEmbedding(TimestampMixin, Base):
    """The vector form of one item's text, used to find similar feedback."""

    __tablename__ = "item_embeddings"
    __table_args__ = (
        Index(
            "ix_item_embeddings_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_items.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    model: Mapped[str] = mapped_column(String(100))
    # The item's content_hash when it was embedded; a mismatch means the text changed since.
    content_hash: Mapped[str] = mapped_column(String(64))


class Theme(TimestampMixin, Base):
    """A group of feedback items about the same thing."""

    __tablename__ = "themes"
    __table_args__ = (
        CheckConstraint(_one_of("status", THEME_STATUSES), name="status"),
        Index("ix_themes_workspace_id_item_count", "workspace_id", "item_count"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    # The middle of the group: new items close to this one belong here.
    centroid: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    item_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which model named it, or "medoid" when the name is borrowed from its most typical item.
    name_model: Mapped[str] = mapped_column(String(100), default="", server_default="")
    renamed_by_human: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


class ThemeItem(Base):
    """Which theme an item belongs to. An item belongs to at most one."""

    __tablename__ = "theme_items"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_items.id", ondelete="CASCADE"), primary_key=True
    )
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # How close this item is to the theme's centre, from 0 to 1.
    similarity: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ThemeWeeklyStat(Base):
    """How many reports a theme received each week, for trend charts and alerts."""

    __tablename__ = "theme_weekly_stats"

    theme_id: Mapped[int] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True
    )
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    item_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))


class EvalLabel(TimestampMixin, Base):
    """The label we treat as correct for an item, used to measure tagging accuracy.

    Drafts come from the source's own labels (e.g. GitHub's "bug"); a person reviewing an
    item in the inbox replaces the draft with a checked label.
    """

    __tablename__ = "eval_labels"
    __table_args__ = (
        CheckConstraint(_one_of("source", EVAL_LABEL_SOURCES), name="source"),
        CheckConstraint(_one_of("expected_type", TAG_TYPES), name="expected_type"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_items.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    expected_type: Mapped[str | None] = mapped_column(String(20))
    expected_area: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(20))


class Alert(Base):
    """A theme that suddenly grew. One alert per theme per week, so nobody is spammed."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("theme_id", "week_start"),
        CheckConstraint(_one_of("status", ALERT_STATUSES), name="status"),
        Index("ix_alerts_workspace_id_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date)
    item_count: Mapped[int] = mapped_column()
    # The usual weekly rate this was compared against, and how many times higher it is.
    baseline: Mapped[float] = mapped_column(Float)
    ratio: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default=text("'pending'")
    )
    channel: Mapped[str] = mapped_column(String(20), default="", server_default="")
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Question(Base):
    """A question asked about the feedback, with the answer and the reports it cited."""

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_workspace_id_created_at", "workspace_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # The reports the answer pointed at, and how many it was shown.
    cited_item_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default=text("'{}'")
    )
    considered_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    enough_evidence: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    # Set when a reader says whether the answer helped.
    helpful: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCall(Base):
    """One request to an AI model, kept for cost, latency and failure tracking."""

    __tablename__ = "ai_calls"
    __table_args__ = (Index("ix_ai_calls_workspace_id_created_at", "workspace_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    feature: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    items_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # Includes thinking tokens, which are billed as output.
    output_tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    latency_ms: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    succeeded: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class Ticket(TimestampMixin, Base):
    """A draft issue for a theme. It is only filed after a person approves it."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(_one_of("status", TICKET_STATUSES), name="status"),
        Index("ix_tickets_workspace_id_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20), default="github", server_default="github")
    # Where it would be filed, e.g. "my-name/my-repo".
    repo: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default=text("'draft'"))
    # Existing issues that look like this one, found before filing.
    duplicate_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    external_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
