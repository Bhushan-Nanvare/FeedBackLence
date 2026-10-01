from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.alerts.delivery import DeliveryStats, build_message, send_pending_alerts
from app.alerts.detection import check_trends, find_rising_themes, record_alerts
from app.config import Settings
from app.main import app
from app.models import Alert, Theme, ThemeWeeklyStat, Workspace

MakeTheme = Callable[..., Theme]
LATEST_WEEK = date(2026, 9, 21)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_theme(db: Session, workspace: Workspace) -> MakeTheme:
    def make(name: str, weekly: list[int], *, status: str = "open") -> Theme:
        """`weekly` is the counts for the weeks ending at LATEST_WEEK, oldest first."""
        theme = Theme(
            workspace_id=workspace.id,
            name=name,
            centroid=[0.0] * EMBEDDING_DIMENSIONS,
            item_count=sum(weekly),
            status=status,
            name_model="medoid",
        )
        db.add(theme)
        db.flush()
        for offset, count in enumerate(reversed(weekly)):
            if count:
                db.add(
                    ThemeWeeklyStat(
                        theme_id=theme.id,
                        week_start=LATEST_WEEK - timedelta(weeks=offset),
                        item_count=count,
                    )
                )
        db.commit()
        return theme

    return make


class FakeSender:
    channel = "slack"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("webhook refused")


def test_a_theme_tripling_its_usual_rate_is_rising(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    rising_theme = make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    make_theme("Steady theme", [8, 8, 8, 8, 9])

    rising = find_rising_themes(db, workspace.id)

    assert [found.theme.id for found in rising] == [rising_theme.id]
    found = rising[0]
    assert (found.item_count, found.week_start) == (9, LATEST_WEEK)
    assert found.ratio == pytest.approx(9.0)


def test_small_numbers_do_not_count_as_a_spike(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Tiny but tripled", [0, 0, 0, 1, 4])

    assert find_rising_themes(db, workspace.id) == []
    # Lowering the bar finds it, which shows the rule and not a missing theme is the reason.
    assert len(find_rising_themes(db, workspace.id, min_items=4)) == 1


def test_a_brand_new_theme_counts_against_one_report_a_week(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Brand new problem", [0, 0, 0, 0, 10])

    found = find_rising_themes(db, workspace.id)[0]

    assert found.baseline == 1.0
    assert found.ratio == pytest.approx(10.0)


def test_hidden_themes_and_quiet_weeks_are_left_alone(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Hidden", [1, 1, 1, 1, 20], status="ignored")
    noisy_but_old = make_theme("Old spike", [1, 1, 1, 20, 0])
    db.add(ThemeWeeklyStat(theme_id=noisy_but_old.id, week_start=LATEST_WEEK, item_count=0))
    db.commit()

    assert find_rising_themes(db, workspace.id) == []


def test_one_alert_per_theme_per_week(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Terminal crashes", [1, 1, 1, 1, 9])

    first = check_trends(db, workspace.id)
    second = check_trends(db, workspace.id)

    assert (first.rising, first.new_alerts) == (1, 1)
    assert (second.rising, second.new_alerts) == (1, 0)
    assert len(db.scalars(select(Alert)).all()) == 1


def test_alerts_are_sent_and_marked(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    theme = make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    record_alerts(db, workspace.id, find_rising_themes(db, workspace.id))
    sender = FakeSender()

    stats = send_pending_alerts(db, workspace.id, sender)

    assert stats == DeliveryStats(sent=1)
    assert theme.name in sender.messages[0]
    assert "9 reports in the week of" in sender.messages[0]
    assert "9.0x the usual" in sender.messages[0]
    alert = db.scalars(select(Alert)).one()
    assert (alert.status, alert.channel) == ("sent", "slack")
    assert alert.sent_at is not None


def test_a_failed_send_is_recorded_not_lost(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    record_alerts(db, workspace.id, find_rising_themes(db, workspace.id))

    stats = send_pending_alerts(db, workspace.id, FakeSender(fail=True))

    assert stats == DeliveryStats(failed=1)
    alert = db.scalars(select(Alert)).one()
    assert (alert.status, alert.error) == ("failed", "webhook refused")


def test_without_a_channel_alerts_are_only_recorded(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    record_alerts(db, workspace.id, find_rising_themes(db, workspace.id))

    stats = send_pending_alerts(db, workspace.id, None)

    assert stats == DeliveryStats(skipped=1)
    alert = db.scalars(select(Alert)).one()
    assert (alert.status, alert.channel) == ("skipped", "none")


def test_message_links_to_the_theme_when_the_app_has_an_address(
    db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    theme = make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    record_alerts(db, workspace.id, find_rising_themes(db, workspace.id))
    alert = db.scalars(select(Alert)).one()

    without_url = build_message(alert, theme, Settings(public_web_url=None))
    with_url = build_message(alert, theme, Settings(public_web_url="https://example.com/"))

    assert "http" not in without_url
    assert f"https://example.com/workspaces/demo/themes/{theme.id}" in with_url


def test_alerts_endpoint_lists_rising_themes(
    client: TestClient, db: Session, workspace: Workspace, make_theme: MakeTheme
) -> None:
    theme = make_theme("Terminal crashes", [1, 1, 1, 1, 9])
    check_trends(db, workspace.id)

    body = client.get("/workspaces/test/alerts").json()

    assert len(body) == 1
    assert body[0]["theme_name"] == theme.name
    assert body[0]["item_count"] == 9
    assert body[0]["ratio"] == pytest.approx(9.0)


def test_check_endpoint_queues_a_single_job(client: TestClient, workspace: Workspace) -> None:
    first = client.post("/workspaces/test/alerts/check")
    second = client.post("/workspaces/test/alerts/check")

    assert first.status_code == 202
    assert first.json()["kind"] == "check_trends"
    assert second.json()["id"] == first.json()["id"]
