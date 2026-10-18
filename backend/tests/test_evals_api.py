"""Tests for the evaluation report endpoint (GET /workspaces/{slug}/evals).

The eval system scores AI tags against human-checked labels.  These tests
insert eval labels and item tags directly, then verify the API returns the
correct accuracy numbers.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import EvalLabel, FeedbackItem, ItemTag, Workspace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_eval_label(
    db: Session,
    item: FeedbackItem,
    *,
    expected_type: str | None = None,
    expected_area: str | None = None,
    source: str = "human",
) -> EvalLabel:
    """Insert a checked label for an item."""
    label = EvalLabel(
        item_id=item.id,
        workspace_id=item.workspace_id,
        expected_type=expected_type,
        expected_area=expected_area,
        source=source,
    )
    db.add(label)
    db.commit()
    return label


def _add_item_tag(
    db: Session,
    item: FeedbackItem,
    *,
    tag_type: str = "bug",
    area: str = "terminal",
    reviewed_by_human: bool = False,
) -> ItemTag:
    """Insert an AI-generated tag for an item."""
    tag = ItemTag(
        item_id=item.id,
        type=tag_type,
        area=area,
        model="test-model",
        prompt_version="v1",
        reviewed_by_human=reviewed_by_human,
    )
    db.add(tag)
    db.commit()
    return tag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvalsEndpoint:
    """GET /workspaces/{slug}/evals"""

    def test_empty_workspace_returns_zero_counts(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """A workspace with no eval labels should return zeroes, not an error."""
        resp = client.get("/workspaces/test/evals")

        assert resp.status_code == 200
        body = resp.json()
        assert body["workspace"] == "test"
        assert body["labelled_items"] == 0
        assert body["scored_items"] == 0
        assert body["fields"]["type"]["compared"] == 0
        assert body["fields"]["area"]["compared"] == 0

    def test_correct_tags_show_full_accuracy(
        self, client: TestClient, db: Session, workspace: Workspace, make_item
    ) -> None:
        """When AI tags match the checked labels, accuracy should be 1.0."""
        item = make_item(1)
        _add_eval_label(db, item, expected_type="bug", expected_area="terminal")
        _add_item_tag(db, item, tag_type="bug", area="terminal")

        body = client.get("/workspaces/test/evals").json()

        assert body["scored_items"] == 1
        assert body["fields"]["type"]["accuracy"] == 1.0
        assert body["fields"]["type"]["correct"] == 1
        assert body["fields"]["area"]["accuracy"] == 1.0

    def test_wrong_tags_reduce_accuracy(
        self, client: TestClient, db: Session, workspace: Workspace, make_item
    ) -> None:
        """When AI tags do NOT match, accuracy should be below 1.0."""
        item1 = make_item(1)
        item2 = make_item(2)
        # item1: correct
        _add_eval_label(db, item1, expected_type="bug")
        _add_item_tag(db, item1, tag_type="bug")
        # item2: wrong
        _add_eval_label(db, item2, expected_type="feature_request")
        _add_item_tag(db, item2, tag_type="bug")

        body = client.get("/workspaces/test/evals").json()
        type_score = body["fields"]["type"]

        assert type_score["compared"] == 2
        assert type_score["correct"] == 1
        assert type_score["accuracy"] == 0.5

    def test_human_corrected_tags_are_excluded(
        self, client: TestClient, db: Session, workspace: Workspace, make_item
    ) -> None:
        """Tags reviewed by a person should be skipped — scoring them flatters the model."""
        item = make_item(1)
        _add_eval_label(db, item, expected_type="bug")
        _add_item_tag(db, item, tag_type="bug", reviewed_by_human=True)

        body = client.get("/workspaces/test/evals").json()

        assert body["skipped_corrected"] == 1
        assert body["scored_items"] == 0

    def test_per_class_breakdown_is_included(
        self, client: TestClient, db: Session, workspace: Workspace, make_item
    ) -> None:
        """The per_class dict should have entries for each label value."""
        item = make_item(1)
        _add_eval_label(db, item, expected_type="bug")
        _add_item_tag(db, item, tag_type="bug")

        body = client.get("/workspaces/test/evals").json()
        per_class = body["fields"]["type"]["per_class"]

        assert "bug" in per_class
        assert per_class["bug"]["expected"] == 1
        assert per_class["bug"]["precision"] == 1.0
        assert per_class["bug"]["recall"] == 1.0

    def test_mistakes_are_listed(
        self, client: TestClient, db: Session, workspace: Workspace, make_item
    ) -> None:
        """Mismatches should appear in the mistakes list."""
        item = make_item(1)
        _add_eval_label(db, item, expected_type="feature_request")
        _add_item_tag(db, item, tag_type="bug")

        body = client.get("/workspaces/test/evals").json()
        mistakes = body["fields"]["type"]["mistakes"]

        assert len(mistakes) >= 1
        # Each mistake is [expected, predicted, count].
        assert mistakes[0][0] == "feature_request"
        assert mistakes[0][1] == "bug"
        assert mistakes[0][2] == 1
