from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FeedbackItem, Job, Source
from app.sources.github_client import GithubIssue
from app.sources.github_sync import CURSOR_OVERLAP, sync_github_source

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def make_issue(
    number: int,
    created: datetime,
    *,
    updated: datetime | None = None,
    body: str = "The editor freezes.",
    labels: list[str] | None = None,
) -> GithubIssue:
    return GithubIssue(
        number=number,
        url=f"https://github.com/acme/app/issues/{number}",
        title=f"Issue {number}",
        body=body,
        author_login=f"user{number}",
        author_is_maintainer=False,
        state="open",
        state_reason=None,
        labels=labels or [],
        comments_count=0,
        reactions_count=0,
        created_at=created,
        updated_at=updated or created,
    )


class FakeClient:
    def __init__(self, pages: list[list[GithubIssue]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []
        self.pages_served = 0

    def iter_issue_pages(
        self, owner: str, repo: str, *, sort: str, direction: str, since: datetime | None = None
    ) -> Iterator[list[GithubIssue]]:
        self.calls.append(
            {"owner": owner, "repo": repo, "sort": sort, "direction": direction, "since": since}
        )
        for page in self.pages:
            self.pages_served += 1
            yield page


def stored_items(db: Session) -> dict[str, FeedbackItem]:
    db.expire_all()
    return {item.external_id: item for item in db.scalars(select(FeedbackItem))}


def test_backfill_stops_at_the_window_and_saves_a_cursor(db: Session, source: Source) -> None:
    client = FakeClient(
        [
            [make_issue(5, days_ago(1)), make_issue(4, days_ago(4))],
            [make_issue(3, days_ago(6)), make_issue(2, days_ago(8))],
            [make_issue(1, days_ago(10))],
        ]
    )

    stats = sync_github_source(db, source, client, now=NOW)

    assert (stats.created, stats.skipped_outside_window) == (3, 1)
    assert client.pages_served == 2
    assert (client.calls[0]["sort"], client.calls[0]["direction"]) == ("created", "desc")
    assert sorted(stored_items(db)) == ["3", "4", "5"]
    assert source.state == {
        "window_start": days_ago(7).isoformat(),
        "cursor": (NOW - CURSOR_OVERLAP).isoformat(),
    }
    assert source.last_synced_at == NOW


def test_backfill_respects_max_items(db: Session, source: Source) -> None:
    source.config = {**source.config, "max_items": 2}
    db.commit()
    client = FakeClient(
        [
            [make_issue(3, days_ago(1)), make_issue(2, days_ago(2)), make_issue(1, days_ago(3))],
            [make_issue(0, days_ago(4))],
        ]
    )

    stats = sync_github_source(db, source, client, now=NOW)

    assert stats.created == 2
    assert client.pages_served == 1
    assert sorted(stored_items(db)) == ["2", "3"]


def test_incremental_sync_is_idempotent_and_detects_changes(db: Session, source: Source) -> None:
    sync_github_source(
        db, source, FakeClient([[make_issue(2, days_ago(2)), make_issue(1, days_ago(3))]]), now=NOW
    )
    original_hash = stored_items(db)["1"].content_hash

    later = NOW + timedelta(hours=6)
    client = FakeClient(
        [
            [
                make_issue(2, days_ago(2), updated=later, labels=["bug"]),
                make_issue(1, days_ago(3), updated=later, body="The editor freezes after saving."),
                make_issue(9, days_ago(30), updated=later),
            ]
        ]
    )
    stats = sync_github_source(db, source, client, now=later)

    assert client.calls[0] == {
        "owner": "acme",
        "repo": "app",
        "sort": "updated",
        "direction": "asc",
        "since": NOW - CURSOR_OVERLAP,
    }
    assert (stats.created, stats.updated, stats.unchanged, stats.skipped_outside_window) == (
        0,
        1,
        1,
        1,
    )
    items = stored_items(db)
    assert sorted(items) == ["1", "2"]
    assert items["1"].content_hash != original_hash
    assert items["1"].body_clean == "The editor freezes after saving."
    assert items["2"].labels == ["bug"]
    assert db.scalar(select(func.count()).select_from(FeedbackItem)) == 2


def test_sync_queues_follow_up_work_only_when_items_change(db: Session, source: Source) -> None:
    sync_github_source(db, source, FakeClient([[make_issue(1, days_ago(1))]]), now=NOW)

    jobs = list(db.scalars(select(Job)))
    assert sorted(job.kind for job in jobs) == ["embed_items", "tag_items"]
    assert {job.payload["workspace_id"] for job in jobs} == {source.workspace_id}

    for job in jobs:
        job.status = "done"
    db.commit()
    later = NOW + timedelta(hours=1)
    unchanged = make_issue(1, days_ago(1), updated=later)
    sync_github_source(db, source, FakeClient([[unchanged]]), now=later)

    assert db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued")) == 0


def test_stores_cleaned_text_and_pseudonymous_author(db: Session, source: Source) -> None:
    issue = make_issue(1, days_ago(1), body="<!-- template -->\nButton is invisible in dark theme.")

    sync_github_source(db, source, FakeClient([[issue]]), now=NOW)

    item = stored_items(db)["1"]
    assert item.body_clean == "Button is invisible in dark theme."
    assert item.body_raw == issue.body
    assert "user1" not in item.author_hash
    assert item.workspace_id == source.workspace_id
