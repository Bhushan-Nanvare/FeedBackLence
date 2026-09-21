from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evals.dataset import build_draft_labels, record_checked_label
from app.models import EvalLabel, FeedbackItem, Workspace

MakeItem = Callable[..., FeedbackItem]


def labels_by_item(db: Session) -> dict[int, EvalLabel]:
    db.expire_all()
    return {label.item_id: label for label in db.scalars(select(EvalLabel))}


def with_labels(db: Session, item: FeedbackItem, labels: list[str]) -> FeedbackItem:
    item.labels = labels
    db.commit()
    return item


def test_drafts_labels_from_source_labels(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    bug = with_labels(db, make_item(1), ["bug", "terminal"])
    request = with_labels(db, make_item(2), ["feature-request"])
    with_labels(db, make_item(3), ["triage-needed"])
    with_labels(db, make_item(4, maintainer=True), ["bug"])
    make_item(5)

    stats = build_draft_labels(db, workspace.id)

    assert (stats.created, stats.no_usable_labels) == (2, 1)
    labels = labels_by_item(db)
    assert sorted(labels) == sorted([bug.id, request.id])
    assert (labels[bug.id].expected_type, labels[bug.id].expected_area) == ("bug", "terminal")
    assert labels[request.id].expected_area is None
    assert labels[bug.id].source == "github_label"


def test_running_twice_updates_instead_of_duplicating(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = with_labels(db, make_item(1), ["bug"])
    build_draft_labels(db, workspace.id)

    with_labels(db, item, ["feature-request", "terminal"])
    stats = build_draft_labels(db, workspace.id)

    assert (stats.created, stats.updated) == (0, 1)
    label = labels_by_item(db)[item.id]
    assert (label.expected_type, label.expected_area) == ("feature_request", "terminal")


def test_respects_the_limit(db: Session, workspace: Workspace, make_item: MakeItem) -> None:
    newest = with_labels(db, make_item(2), ["bug"])
    with_labels(db, make_item(1), ["bug"])

    build_draft_labels(db, workspace.id, limit=1)

    assert list(labels_by_item(db)) == [newest.id]


def test_checked_labels_are_never_replaced_by_drafts(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = with_labels(db, make_item(1), ["bug"])
    record_checked_label(
        db,
        item_id=item.id,
        workspace_id=workspace.id,
        expected_type="question",
        expected_area="editor",
    )
    db.commit()

    build_draft_labels(db, workspace.id)

    label = labels_by_item(db)[item.id]
    assert (label.expected_type, label.expected_area, label.source) == (
        "question",
        "editor",
        "human",
    )


def test_a_correction_keeps_fields_it_does_not_change(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1)
    record_checked_label(
        db,
        item_id=item.id,
        workspace_id=workspace.id,
        expected_type="bug",
        expected_area="editor",
    )
    record_checked_label(
        db, item_id=item.id, workspace_id=workspace.id, expected_type=None, expected_area="terminal"
    )
    db.commit()

    label = labels_by_item(db)[item.id]
    assert (label.expected_type, label.expected_area) == ("bug", "terminal")
