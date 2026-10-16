"""Tests for the AI cost tracking endpoint (GET /workspaces/{slug}/ai/usage).

The ai_calls table is already populated by the tagging, embedding and
answering modules whenever they call a model.  These tests insert rows
directly and verify that the aggregation endpoint returns the right totals.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AiCall, Workspace

# ---------------------------------------------------------------------------
# Helpers — insert ai_call rows with sensible defaults so each test only
# specifies the fields it cares about.
# ---------------------------------------------------------------------------


def _add_call(
    db: Session,
    workspace: Workspace,
    *,
    feature: str = "tagging",
    model: str = "gemini-3.5-flash-lite",
    items_count: int = 10,
    input_tokens: int = 500,
    output_tokens: int = 100,
    latency_ms: int = 200,
    succeeded: bool = True,
    created_at: datetime | None = None,
) -> AiCall:
    """Insert one ai_call row and flush so it gets an id."""
    call = AiCall(
        workspace_id=workspace.id,
        feature=feature,
        model=model,
        items_count=items_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        succeeded=succeeded,
    )
    # Override the server default for created_at when the test needs a
    # specific date (used by the daily-breakdown tests).
    if created_at is not None:
        call.created_at = created_at
    db.add(call)
    db.commit()
    return call


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUsageEndpoint:
    """GET /workspaces/{slug}/ai/usage"""

    def test_empty_workspace_returns_zeroes(self, client: TestClient, workspace: Workspace) -> None:
        """A workspace with no AI calls should return all zeroes, not an error."""
        body = client.get("/workspaces/test/ai/usage").json()

        assert body["total_calls"] == 0
        assert body["succeeded_calls"] == 0
        assert body["total_items"] == 0
        assert body["input_tokens"] == 0
        assert body["output_tokens"] == 0
        assert body["total_tokens"] == 0
        assert body["estimated_cost_usd"] == 0.0
        assert body["by_feature"] == []
        assert body["daily"] == []

    def test_lifetime_totals_sum_all_calls(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Two calls should produce summed lifetime totals."""
        _add_call(db, workspace, input_tokens=1000, output_tokens=200, items_count=10)
        _add_call(db, workspace, input_tokens=500, output_tokens=100, items_count=5)

        body = client.get("/workspaces/test/ai/usage").json()

        assert body["total_calls"] == 2
        assert body["succeeded_calls"] == 2
        assert body["total_items"] == 15
        assert body["input_tokens"] == 1500
        assert body["output_tokens"] == 300
        # total_tokens is just input + output for convenience.
        assert body["total_tokens"] == 1800
        # Estimated cost should be > 0 when there are tokens.
        assert body["estimated_cost_usd"] > 0

    def test_failed_calls_are_counted_separately(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Failed calls count toward total_calls but not succeeded_calls."""
        _add_call(db, workspace, succeeded=True)
        _add_call(db, workspace, succeeded=False)
        _add_call(db, workspace, succeeded=False)

        body = client.get("/workspaces/test/ai/usage").json()

        assert body["total_calls"] == 3
        assert body["succeeded_calls"] == 1

    def test_feature_breakdown(self, client: TestClient, db: Session, workspace: Workspace) -> None:
        """Each distinct feature value gets its own row in by_feature."""
        _add_call(db, workspace, feature="tagging", input_tokens=1000, items_count=10)
        _add_call(db, workspace, feature="tagging", input_tokens=2000, items_count=20)
        _add_call(db, workspace, feature="embedding", input_tokens=500, items_count=50)
        _add_call(db, workspace, feature="ask", input_tokens=300, items_count=5)

        body = client.get("/workspaces/test/ai/usage").json()
        features = {f["feature"]: f for f in body["by_feature"]}

        # Three distinct features should appear.
        assert set(features.keys()) == {"ask", "embedding", "tagging"}

        # Tagging: two calls summed.
        assert features["tagging"]["total_calls"] == 2
        assert features["tagging"]["input_tokens"] == 3000
        assert features["tagging"]["total_items"] == 30

        # Embedding: one call.
        assert features["embedding"]["total_calls"] == 1
        assert features["embedding"]["total_items"] == 50

    def test_daily_breakdown(self, client: TestClient, db: Session, workspace: Workspace) -> None:
        """Calls on different days produce separate daily rows."""
        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)

        _add_call(db, workspace, input_tokens=100, created_at=today)
        _add_call(db, workspace, input_tokens=200, created_at=today)
        _add_call(db, workspace, input_tokens=300, created_at=yesterday)

        body = client.get("/workspaces/test/ai/usage").json()

        # Two distinct calendar days should appear, most recent first.
        assert len(body["daily"]) == 2
        assert body["daily"][0]["total_calls"] == 2  # today
        assert body["daily"][0]["input_tokens"] == 300  # 100 + 200
        assert body["daily"][1]["total_calls"] == 1  # yesterday
        assert body["daily"][1]["input_tokens"] == 300

    def test_other_workspace_data_is_excluded(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        other_workspace: Workspace,
    ) -> None:
        """Calls in workspace B must not appear in workspace A's usage."""
        _add_call(db, workspace, input_tokens=100)
        _add_call(db, other_workspace, input_tokens=9999)

        body = client.get("/workspaces/test/ai/usage").json()

        # Only the call from the "test" workspace should be counted.
        assert body["total_calls"] == 1
        assert body["input_tokens"] == 100

    def test_days_parameter_limits_daily_window(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """The ?days= parameter controls how many days of daily data come back."""
        now = datetime.now(UTC)
        # Insert a call from 10 days ago.
        _add_call(db, workspace, created_at=now - timedelta(days=10))
        # Insert a call from today.
        _add_call(db, workspace, created_at=now)

        # Ask for only the last 5 days — the 10-day-old call should not appear
        # in the daily breakdown (but it still counts in lifetime totals).
        body = client.get("/workspaces/test/ai/usage?days=5").json()

        assert body["total_calls"] == 2  # lifetime includes everything
        # Daily should only contain today's call.
        assert len(body["daily"]) == 1

    def test_avg_latency_excludes_zero_values(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        """Calls with latency_ms=0 (e.g. never ran) should not drag down the average."""
        _add_call(db, workspace, latency_ms=200, feature="tagging")
        _add_call(db, workspace, latency_ms=400, feature="tagging")
        # A failed call that never reached the model — latency is 0.
        _add_call(db, workspace, latency_ms=0, succeeded=False, feature="tagging")

        body = client.get("/workspaces/test/ai/usage").json()
        tagging = [f for f in body["by_feature"] if f["feature"] == "tagging"][0]

        # Average should be (200 + 400) / 2 = 300, not (200 + 400 + 0) / 3 = 200.
        assert tagging["avg_latency_ms"] == 300.0
