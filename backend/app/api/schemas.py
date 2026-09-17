from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Sentiment, TagType, Urgency

GITHUB_REPO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"
AREA_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"


class GithubSourceCreate(BaseModel):
    repo: str = Field(pattern=GITHUB_REPO_PATTERN, examples=["microsoft/vscode"])
    backfill_days: int = Field(default=30, ge=1, le=365)
    max_items: int = Field(default=2000, ge=1, le=20_000)


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    name: str
    config: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime


class ProductAreaIn(BaseModel):
    slug: str = Field(pattern=AREA_SLUG_PATTERN, examples=["terminal"])
    name: str = Field(min_length=1, max_length=100, examples=["Terminal"])
    description: str = Field(default="", max_length=500, examples=["Integrated terminal, shells"])

    @field_validator("slug")
    @classmethod
    def slug_is_not_reserved(cls, value: str) -> str:
        if value == "other":
            raise ValueError('"other" is reserved for feedback that fits no area')
        return value


class ProductAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str


class TaggingStatus(BaseModel):
    total_items: int
    maintainer_items: int
    tagged_items: int
    reviewed_by_human: int
    pending_items: int
    by_type: dict[str, int]


class ItemTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    area: str
    sentiment: str
    urgency: str
    confidence: float
    summary: str
    reviewed_by_human: bool


class FeedbackItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    url: str
    title: str
    state: str
    state_reason: str | None
    labels: list[str]
    comments_count: int
    reactions_count: int
    author_is_maintainer: bool
    external_created_at: datetime
    tag: ItemTagRead | None


class FeedbackItemDetail(FeedbackItemRead):
    body_clean: str


class ItemPage(BaseModel):
    total: int
    items: list[FeedbackItemRead]


class ItemFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=200)
    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    sentiment: Sentiment | None = None
    urgency: Urgency | None = None
    state: Literal["open", "closed"] | None = None
    untagged: bool = False
    include_maintainer: bool = False
    sort: Literal["newest", "oldest", "most_reactions"] = "newest"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ItemTagUpdate(BaseModel):
    """A person's correction; only the given fields change."""

    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    sentiment: Sentiment | None = None
    urgency: Urgency | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "ItemTagUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give at least one of type, area, sentiment or urgency")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime
