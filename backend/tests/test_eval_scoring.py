from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.evals.dataset import record_checked_label
from app.evals.scoring import build_report, score_field
from app.models import FeedbackItem, ItemTag, Workspace

MakeItem = Callable[..., FeedbackItem]

PAIRS = [
    ("bug", "bug"),
    ("bug", "bug"),
    ("bug", "question"),
    ("feature_request", "feature_request"),
    ("question", "bug"),
]


def test_score_field_counts_accuracy_and_per_label_scores() -> None:
    score = score_field(PAIRS)

    assert (score.compared, score.correct) == (5, 3)
    assert score.accuracy == pytest.approx(0.6)
    # bug F1 = 2/3, feature_request F1 = 1, question F1 = 0
    assert score.macro_f1 == pytest.approx((2 / 3 + 1 + 0) / 3)
    bug = score.per_class["bug"]
    assert (bug.expected, bug.predicted, bug.correct) == (3, 3, 2)
    assert (bug.precision, bug.recall) == (pytest.approx(2 / 3), pytest.approx(2 / 3))
    assert score.mistakes == [("bug", "question", 1), ("question", "bug", 1)]


def test_score_field_with_nothing_to_compare() -> None:
    score = score_field([])

    assert (score.compared, score.accuracy, score.macro_f1) == (0, 0.0, 0.0)


def tag_item(db: Session, item: FeedbackItem, **overrides: object) -> None:
    values = {
        "type": "bug",
        "area": "editor",
        "sentiment": "negative",
        "urgency": "medium",
        "confidence": 0.8,
        "summary": "Something is broken.",
        "content_hash": item.content_hash,
        "model": "gemini-test",
        "prompt_version": "tag-v1",
    }
    values.update(overrides)
    db.add(ItemTag(item_id=item.id, workspace_id=item.workspace_id, **values))
    db.commit()


def test_report_scores_ai_tags_and_leaves_out_corrected_ones(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    right = make_item(1)
    wrong = make_item(2)
    corrected = make_item(3)
    unlabelled = make_item(4)
    tag_item(db, right)
    tag_item(db, wrong, type="question", area="terminal")
    tag_item(db, corrected, reviewed_by_human=True)
    tag_item(db, unlabelled)
    for item in (right, wrong, corrected):
        record_checked_label(
            db,
            item_id=item.id,
            workspace_id=workspace.id,
            expected_type="bug",
            expected_area="editor",
        )
    db.commit()

    report = build_report(db, workspace)

    assert (report.labelled_items, report.scored_items, report.skipped_corrected) == (3, 2, 1)
    assert report.checked_by_people == 3
    assert report.model == "gemini-test"
    assert report.fields["type"].accuracy == pytest.approx(0.5)
    assert report.fields["area"].accuracy == pytest.approx(0.5)


def test_report_without_any_tags_yet(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1)
    record_checked_label(
        db, item_id=item.id, workspace_id=workspace.id, expected_type="bug", expected_area=None
    )
    db.commit()

    report = build_report(db, workspace)

    assert (report.scored_items, report.model) == (0, None)
    assert report.fields["type"].compared == 0
