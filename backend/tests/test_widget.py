"""Tests for the embeddable feedback widget.

The widget has two endpoints:
- POST /workspaces/{slug}/widget/submit — unauthenticated, accepts feedback
- GET  /workspaces/{slug}/widget/embed  — returns the embed snippet

And a backend module (app.sources.widget) that handles PII scrubbing, item
creation and job queueing.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import FeedbackItem, Job, Source, Workspace

# ---------------------------------------------------------------------------
# Helper — build an anonymous test client (no auth headers) since the
# widget submit endpoint is intentionally unauthenticated.
# ---------------------------------------------------------------------------


def anon_client() -> TestClient:
    """A client with no auth headers, simulating an external visitor."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /workspaces/{slug}/widget/submit
# ---------------------------------------------------------------------------


class TestWidgetSubmit:
    """The public submission endpoint."""

    def test_submit_creates_a_feedback_item(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """A simple submission should create a FeedbackItem and return its id."""
        body = {"text": "The search feature is really slow when I type long queries"}

        # Use the authenticated client here — it should also work.
        resp = client.post("/workspaces/test/widget/submit", json=body)

        assert resp.status_code == 201
        data = resp.json()
        assert data["item_id"] > 0
        assert data["message"] == "Thank you for your feedback!"

        # Verify the item was actually saved in the database.
        item = db.get(FeedbackItem, data["item_id"])
        assert item is not None
        assert item.workspace_id == workspace.id
        assert "search" in item.body_clean.lower()

    def test_submit_works_without_authentication(self, db: Session, workspace: Workspace) -> None:
        """The whole point of the widget — anonymous visitors can submit."""
        anon = anon_client()
        resp = anon.post(
            "/workspaces/test/widget/submit",
            json={"text": "I love this product, keep it up!"},
        )

        assert resp.status_code == 201
        assert resp.json()["item_id"] > 0

    def test_submit_scrubs_email_addresses(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """PII must be stripped before anything is stored."""
        resp = client.post(
            "/workspaces/test/widget/submit",
            json={"text": "Contact me at john@example.com about this bug"},
        )

        item = db.get(FeedbackItem, resp.json()["item_id"])
        assert item is not None
        # The email should be replaced with [email], never stored as-is.
        assert "john@example.com" not in item.body_raw
        assert "john@example.com" not in item.body_clean
        assert "[email]" in item.body_raw

    def test_submit_creates_widget_source(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """The first submission should auto-create a Source(kind='widget')."""
        client.post(
            "/workspaces/test/widget/submit",
            json={"text": "This is a test submission for the widget"},
        )

        source = db.scalar(
            select(Source).where(
                Source.workspace_id == workspace.id,
                Source.kind == "widget",
            )
        )
        assert source is not None
        assert source.name == "widget"

    def test_submit_queues_tagging_and_embedding(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """After a submission, tagging and embedding jobs should be queued."""
        client.post(
            "/workspaces/test/widget/submit",
            json={"text": "The dashboard takes forever to load"},
        )

        jobs = list(db.scalars(select(Job).where(Job.workspace_id == workspace.id)))
        job_kinds = {j.kind for j in jobs}
        assert "tag_items" in job_kinds
        assert "embed_items" in job_kinds

    def test_submit_rejects_empty_text(self, client: TestClient, workspace: Workspace) -> None:
        """Text shorter than 3 characters should be rejected."""
        resp = client.post("/workspaces/test/widget/submit", json={"text": "ab"})
        assert resp.status_code == 422

    def test_submit_returns_404_for_unknown_workspace(self, client: TestClient) -> None:
        """Submitting to a non-existent workspace should 404."""
        resp = client.post(
            "/workspaces/nonexistent/widget/submit",
            json={"text": "This workspace does not exist"},
        )
        assert resp.status_code == 404

    def test_duplicate_text_does_not_create_two_items(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Submitting the exact same text twice should create only one item."""
        body = {"text": "Exact same feedback submitted twice"}

        first = client.post("/workspaces/test/widget/submit", json=body)
        second = client.post("/workspaces/test/widget/submit", json=body)

        # Both should succeed (201), but the second is an upsert.
        assert first.status_code == 201
        assert second.status_code == 201

        # Only one FeedbackItem should exist for this text.
        items = list(
            db.scalars(select(FeedbackItem).where(FeedbackItem.workspace_id == workspace.id))
        )
        assert len(items) == 1

    def test_submit_with_optional_name_and_email(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Name and email are accepted but the email is scrubbed from stored text."""
        resp = client.post(
            "/workspaces/test/widget/submit",
            json={
                "text": "Great product!",
                "name": "Alice",
                "email": "alice@example.com",
            },
        )

        assert resp.status_code == 201
        item = db.get(FeedbackItem, resp.json()["item_id"])
        assert item is not None
        # The author hash should be based on the email, not "anonymous".
        assert item.author_hash != ""


# ---------------------------------------------------------------------------
# GET /workspaces/{slug}/widget/embed
# ---------------------------------------------------------------------------


class TestWidgetEmbed:
    """The embed snippet endpoint."""

    def test_returns_embed_snippet(self, client: TestClient, workspace: Workspace) -> None:
        """The embed endpoint should return a ready-to-paste script tag."""
        resp = client.get("/workspaces/test/widget/embed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_slug"] == "test"
        assert "widget.js" in data["script_url"]
        assert 'data-workspace="test"' in data["snippet"]
        assert "<script" in data["snippet"]

    def test_embed_requires_readable_workspace(self) -> None:
        """An anonymous user should not see the embed for a private workspace."""
        anon = anon_client()
        resp = anon.get("/workspaces/test/widget/embed")
        # "test" workspace is private and the client has no auth → 401.
        assert resp.status_code == 401
