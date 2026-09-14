"""Import GitHub issues into feedback_items: a bounded backfill first, then incremental syncs."""

import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FeedbackItem, Source
from app.processing.clean import clean_body
from app.processing.hashing import author_hash, content_hash
from app.sources.github_client import GithubClient, GithubIssue

logger = logging.getLogger(__name__)

GITHUB_SYNC_JOB = "github_sync"

# Next sync re-reads a few minutes before the last one started, so clock skew can't lose
# updates. Re-reading is free because upserts are idempotent.
CURSOR_OVERLAP = timedelta(minutes=5)

# Columns refreshed when an issue we already have is fetched again.
_REFRESHED_COLUMNS = (
    "url",
    "title",
    "body_raw",
    "body_clean",
    "content_hash",
    "author_is_maintainer",
    "state",
    "state_reason",
    "labels",
    "comments_count",
    "reactions_count",
    "external_updated_at",
)


class IssuePager(Protocol):
    def iter_issue_pages(
        self,
        owner: str,
        repo: str,
        *,
        sort: Literal["created", "updated"],
        direction: Literal["asc", "desc"],
        since: datetime | None = None,
    ) -> Iterator[list[GithubIssue]]: ...


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_outside_window: int = 0

    @property
    def processed(self) -> int:
        return self.created + self.updated + self.unchanged


def sync_github_source(
    session: Session, source: Source, client: IssuePager, *, now: datetime | None = None
) -> SyncStats:
    """Fetch new and changed issues for a GitHub source and upsert them.

    The first run walks issues newest-created first until it leaves the backfill window or
    reaches max_items. Later runs only ask GitHub for issues updated since the previous run.
    Only issues created inside the window are kept, so the dataset stays a recent slice.
    """
    now = now or datetime.now(UTC)
    owner, repo = source.config["repo"].split("/", 1)
    max_items: int = source.config["max_items"]
    stats = SyncStats()

    is_backfill = "cursor" not in source.state
    if is_backfill:
        window_start = now - timedelta(days=source.config["backfill_days"])
        pages = client.iter_issue_pages(owner, repo, sort="created", direction="desc")
    else:
        window_start = datetime.fromisoformat(source.state["window_start"])
        since = datetime.fromisoformat(source.state["cursor"])
        pages = client.iter_issue_pages(owner, repo, sort="updated", direction="asc", since=since)

    for page in pages:
        in_window = [issue for issue in page if issue.created_at >= window_start]
        stats.skipped_outside_window += len(page) - len(in_window)
        if is_backfill:
            in_window = in_window[: max_items - stats.processed]
        _upsert(session, source, in_window, stats)
        session.commit()  # keep progress if a later page fails

        # Newest-first order: once one issue is older than the window, all later ones are too.
        if is_backfill and (len(in_window) < len(page) or stats.processed >= max_items):
            break

    source.state = {
        "window_start": window_start.isoformat(),
        "cursor": (now - CURSOR_OVERLAP).isoformat(),
    }
    source.last_synced_at = now
    session.commit()
    return stats


def run_github_sync_job(session: Session, payload: dict[str, Any]) -> None:
    source = session.get(Source, payload["source_id"])
    if source is None:
        logger.warning("source %s no longer exists; nothing to sync", payload["source_id"])
        return
    with GithubClient(token=get_settings().github_token) as client:
        stats = sync_github_source(session, source, client)
    logger.info("synced %s: %s", source.name, asdict(stats))


def _upsert(session: Session, source: Source, issues: list[GithubIssue], stats: SyncStats) -> None:
    if not issues:
        return

    rows = [_row_for(source, issue) for issue in issues]
    known_hashes = dict(
        session.execute(
            select(FeedbackItem.external_id, FeedbackItem.content_hash).where(
                FeedbackItem.source_id == source.id,
                FeedbackItem.external_id.in_([row["external_id"] for row in rows]),
            )
        )
        .tuples()
        .all()
    )
    for row in rows:
        previous_hash = known_hashes.get(row["external_id"])
        if previous_hash is None:
            stats.created += 1
        elif previous_hash != row["content_hash"]:
            stats.updated += 1
        else:
            stats.unchanged += 1

    statement = insert(FeedbackItem).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[FeedbackItem.source_id, FeedbackItem.external_id],
        set_={column: statement.excluded[column] for column in _REFRESHED_COLUMNS}
        | {"updated_at": func.now()},
    )
    session.execute(statement)


def _row_for(source: Source, issue: GithubIssue) -> dict[str, Any]:
    body_clean = clean_body(issue.body)
    return {
        "workspace_id": source.workspace_id,
        "source_id": source.id,
        "external_id": str(issue.number),
        "url": issue.url,
        "title": issue.title,
        "body_raw": issue.body,
        "body_clean": body_clean,
        "content_hash": content_hash(issue.title, body_clean),
        "author_hash": author_hash("github", issue.author_login),
        "author_is_maintainer": issue.author_is_maintainer,
        "state": issue.state,
        "state_reason": issue.state_reason,
        "labels": issue.labels,
        "comments_count": issue.comments_count,
        "reactions_count": issue.reactions_count,
        "external_created_at": issue.created_at,
        "external_updated_at": issue.updated_at,
    }
