from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
