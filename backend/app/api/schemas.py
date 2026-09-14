from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

GITHUB_REPO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"


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
