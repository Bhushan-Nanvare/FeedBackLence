"""Tests for the embeddable feedback widget.

The widget has two endpoints:
- POST /workspaces/{slug}/widget/submit — unauthenticated, accepts feedback
- GET  /workspaces/{slug}/widget/embed  — returns the embed snippet

And a backend module (app.sources.widget) that handles PII scrubbing, item
creation and job queueing.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import FeedbackItem, Job, Membership, Source, User, Workspace

# ---------------------------------------------------------------------------
# Helper — build an anonymous test client (no auth headers) since the
# widget submit endpoint is intentionally unauthenticated.
# ---------------------------------------------------------------------------


def anon_client() -> TestClient:
    """A client with no auth headers, simulating an external visitor."""
    return TestClient(app)


@pytest.fixture
def widget_on(db: Session, workspace: Workspace) -> Source:
    """The widget switched on, as an owner would from the import page."""
    source = Source(
        workspace_id=workspace.id, kind="widget", name="widget", config={"enabled": True}
    )
    db.add(source)
    db.commit()
    return source


# ---------------------------------------------------------------------------
# POST /workspaces/{slug}/widget/submit
# ---------------------------------------------------------------------------


class TestWidgetSubmit:
    """The public submission endpoint."""

    def test_submit_creates_a_feedback_item(
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
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

    def test_submit_works_without_authentication(
        self, db: Session, workspace: Workspace, widget_on: Source
    ) -> None:
        """The whole point of the widget — anonymous visitors can submit."""
        anon = anon_client()
        resp = anon.post(
            "/workspaces/test/widget/submit",
            json={"text": "I love this product, keep it up!"},
        )

        assert resp.status_code == 201
        assert resp.json()["item_id"] > 0

    def test_submit_scrubs_email_addresses(
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
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

    def test_submit_is_refused_until_the_widget_is_turned_on(
        self, db: Session, workspace: Workspace
    ) -> None:
        """Nobody can push feedback into a workspace that never asked for a widget."""
        resp = anon_client().post(
            "/workspaces/test/widget/submit",
            json={"text": "Feedback nobody asked for"},
        )

        assert resp.status_code == 404
        assert db.scalars(select(FeedbackItem)).all() == []

    def test_turning_the_widget_on_opens_it_to_strangers(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """An owner switches it on, and only then are submissions accepted."""
        turned_on = client.post("/workspaces/test/widget/enable", json={"enabled": True})

        assert turned_on.status_code == 200
        assert turned_on.json()["enabled"] is True
        source = db.scalar(
            select(Source).where(
                Source.workspace_id == workspace.id,
                Source.kind == "widget",
            )
        )
        assert source is not None and source.config["enabled"] is True
        assert (
            anon_client()
            .post("/workspaces/test/widget/submit", json={"text": "Now the widget is live"})
            .status_code
            == 201
        )

    def test_turning_the_widget_off_stops_submissions_but_keeps_feedback(
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
    ) -> None:
        """Switching off closes the door; what came through it stays."""
        anon_client().post("/workspaces/test/widget/submit", json={"text": "Collected while on"})

        client.post("/workspaces/test/widget/enable", json={"enabled": False})

        refused = anon_client().post(
            "/workspaces/test/widget/submit", json={"text": "Sent after the switch off"}
        )
        assert refused.status_code == 404
        assert len(db.scalars(select(FeedbackItem)).all()) == 1

    def test_submit_queues_tagging_and_embedding(
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
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
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
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
        self, client: TestClient, db: Session, workspace: Workspace, widget_on: Source
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
        # Looking at the snippet does not switch the widget on.
        assert data["enabled"] is False

    def test_embed_is_for_owners_and_admins_only(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Turning the widget on decides who may write, so members cannot do it."""
        token = (
            anon_client()
            .post(
                "/auth/register",
                json={"email": "m@example.com", "name": "M", "password": "a-good-password"},
            )
            .json()["access_token"]
        )
        user = db.scalar(select(User).where(User.email == "m@example.com"))
        assert user is not None
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="member"))
        db.commit()
        member = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        assert anon_client().get("/workspaces/test/widget/embed").status_code == 401
        assert member.get("/workspaces/test/widget/embed").status_code == 403
        assert client.get("/workspaces/test/widget/embed").status_code == 200
