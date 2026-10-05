from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import FeedbackItem, Job, Source, Workspace
from app.processing.privacy import scrub_personal_data
from app.sources.csv_import import import_csv

Import = Callable[..., tuple[Source, object]]

SIMPLE_CSV = """title,text,created_at
Terminal crashes,It dies when I split a pane,2026-09-01
Chat is slow,The chat panel takes ages,2026-09-02
"""


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def items(db: Session) -> list[FeedbackItem]:
    db.expire_all()
    return list(db.scalars(select(FeedbackItem).order_by(FeedbackItem.external_id)))


def test_reads_a_simple_file(db: Session, workspace: Workspace) -> None:
    source, stats = import_csv(db, workspace, filename="support.csv", content=SIMPLE_CSV)

    assert (stats.created, stats.skipped, stats.problems) == (2, 0, [])
    assert (source.kind, source.name) == ("csv", "support.csv")
    stored = items(db)
    assert {item.title for item in stored} == {"Terminal crashes", "Chat is slow"}
    first = next(item for item in stored if item.title == "Terminal crashes")
    assert first.body_clean == "It dies when I split a pane"
    assert first.external_created_at == datetime(2026, 9, 1, tzinfo=UTC)


def test_recognises_differently_named_columns(db: Session, workspace: Workspace) -> None:
    content = (
        "Ticket ID,Subject,Description,Submitted At\n42,Login fails,I cannot sign in,2026-09-03\n"
    )

    _, stats = import_csv(db, workspace, filename="zendesk.csv", content=content)

    item = items(db)[0]
    assert stats.created == 1
    assert (item.external_id, item.title) == ("42", "Login fails")
    assert item.body_clean == "I cannot sign in"


def test_a_row_without_text_is_reported_not_dropped_silently(
    db: Session, workspace: Workspace
) -> None:
    content = "title,text\nFine row,Something happened\nEmpty row,\n"

    _, stats = import_csv(db, workspace, filename="mixed.csv", content=content)

    assert (stats.created, stats.skipped) == (1, 1)
    assert stats.problems == ["Row 3 has no text."]


def test_a_file_without_a_text_column_explains_itself(db: Session, workspace: Workspace) -> None:
    _, stats = import_csv(db, workspace, filename="wrong.csv", content="name,score\nAda,10\n")

    assert stats.created == 0
    assert "No text column found" in stats.problems[0]
    assert items(db) == []


def test_importing_the_same_file_twice_does_not_duplicate(
    db: Session, workspace: Workspace
) -> None:
    import_csv(db, workspace, filename="support.csv", content=SIMPLE_CSV)

    _, stats = import_csv(db, workspace, filename="support.csv", content=SIMPLE_CSV)

    assert (stats.created, stats.unchanged) == (0, 2)
    assert len(items(db)) == 2


def test_an_edited_row_updates_the_existing_item(db: Session, workspace: Workspace) -> None:
    content = "id,title,text\n7,Terminal crashes,It dies on split\n"
    import_csv(db, workspace, filename="support.csv", content=content)

    edited = "id,title,text\n7,Terminal crashes,It dies on split and loses my output\n"
    _, stats = import_csv(db, workspace, filename="support.csv", content=edited)

    assert (stats.created, stats.updated) == (0, 1)
    assert items(db)[0].body_clean == "It dies on split and loses my output"


def test_personal_details_are_removed_before_anything_is_stored(
    db: Session, workspace: Workspace
) -> None:
    content = (
        "title,text\n"
        "Cannot log in,"
        '"Write to me at ada@example.com or call +1 (555) 123-4567 please"\n'
    )

    import_csv(db, workspace, filename="support.csv", content=content)

    item = items(db)[0]
    assert "ada@example.com" not in item.body_raw
    assert "555" not in item.body_raw
    assert item.body_clean == "Write to me at [email] or call [phone] please"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Released on 2026-09-18 for everyone", "Released on 2026-09-18 for everyone"),
        ("Version 1.122.1 broke it", "Version 1.122.1 broke it"),
        ("Call 07700 900123 now", "Call [phone] now"),
        ("mail me: a.b+tag@sub.example.co.uk", "mail me: [email]"),
    ],
)
def test_scrubbing_leaves_dates_and_versions_alone(text: str, expected: str) -> None:
    assert scrub_personal_data(text) == expected


def test_import_queues_tagging_and_grouping(db: Session, workspace: Workspace) -> None:
    import_csv(db, workspace, filename="support.csv", content=SIMPLE_CSV)

    queued = sorted(job.kind for job in db.scalars(select(Job)))

    assert queued == ["embed_items", "tag_items"]


def test_upload_endpoint_reports_what_happened(client: TestClient, workspace: Workspace) -> None:
    response = client.post(
        "/workspaces/test/sources/csv",
        files={"file": ("support.csv", SIMPLE_CSV.encode(), "text/csv")},
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["created"], body["skipped"]) == (2, 0)
    assert body["source"]["name"] == "support.csv"
    assert body["source"]["kind"] == "csv"


def test_upload_endpoint_refuses_an_empty_file(client: TestClient, workspace: Workspace) -> None:
    response = client.post(
        "/workspaces/test/sources/csv", files={"file": ("empty.csv", b"  ", "text/csv")}
    )

    assert response.status_code == 422
