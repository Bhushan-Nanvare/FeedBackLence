"""Spot themes that suddenly grew, and record one alert per theme per week."""

import logging
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.alerts.delivery import get_sender, send_pending_alerts
from app.config import get_settings
from app.jobs import queue
from app.models import Alert, Job, Theme, ThemeWeeklyStat
from app.themes.trends import COMPARISON_WEEKS, WeekCount, fill_missing_weeks

logger = logging.getLogger(__name__)

CHECK_TRENDS_JOB = "check_trends"
# A quiet theme's usual rate is treated as at least one report a week, so a brand new
# problem with eight reports counts as eight times usual instead of dividing by zero.
MIN_BASELINE = 1.0


@dataclass(frozen=True)
class RisingTheme:
    theme: Theme
    week_start: date
    item_count: int
    baseline: float
    ratio: float


@dataclass
class TrendStats:
    themes_checked: int = 0
    rising: int = 0
    new_alerts: int = 0


def request_trend_check(session: Session, workspace_id: int) -> Job:
    """Queue a trend check, reusing one that hasn't started yet. The caller commits."""
    payload = {"workspace_id": workspace_id}
    existing = queue.find_active(session, CHECK_TRENDS_JOB, payload, statuses=("queued",))
    return existing or queue.enqueue(session, CHECK_TRENDS_JOB, payload, workspace_id=workspace_id)


def run_check_trends_job(session: Session, payload: dict[str, Any]) -> None:
    workspace_id = payload["workspace_id"]
    stats = check_trends(session, workspace_id)
    delivery = send_pending_alerts(session, workspace_id, get_sender())
    logger.info(
        "checked trends for workspace %s: %s, delivery %s",
        workspace_id,
        asdict(stats),
        asdict(delivery),
    )


def check_trends(
    session: Session,
    workspace_id: int,
    *,
    min_ratio: float | None = None,
    min_items: int | None = None,
) -> TrendStats:
    rising = find_rising_themes(session, workspace_id, min_ratio=min_ratio, min_items=min_items)
    stats = TrendStats(
        themes_checked=session.scalar(
            select(func.count())
            .select_from(Theme)
            .where(Theme.workspace_id == workspace_id, Theme.item_count > 0)
        )
        or 0,
        rising=len(rising),
    )
    stats.new_alerts = len(record_alerts(session, workspace_id, rising))
    return stats


def find_rising_themes(
    session: Session,
    workspace_id: int,
    *,
    min_ratio: float | None = None,
    min_items: int | None = None,
) -> list[RisingTheme]:
    """Compare each theme's most recent week of data with the weeks before it.

    The comparison uses the newest week the workspace has data for, not today's date, so a
    check still works on an import that finished a few days ago.
    """
    settings = get_settings()
    ratio_threshold = min_ratio if min_ratio is not None else settings.alert_min_ratio
    items_threshold = min_items if min_items is not None else settings.alert_min_items

    latest_week = session.scalar(
        select(func.max(ThemeWeeklyStat.week_start))
        .join(Theme, Theme.id == ThemeWeeklyStat.theme_id)
        .where(Theme.workspace_id == workspace_id)
    )
    if latest_week is None:
        return []

    weeks_by_theme: dict[int, list[WeekCount]] = {}
    for theme_id, week_start, item_count in session.execute(
        select(ThemeWeeklyStat.theme_id, ThemeWeeklyStat.week_start, ThemeWeeklyStat.item_count)
        .join(Theme, Theme.id == ThemeWeeklyStat.theme_id)
        .where(Theme.workspace_id == workspace_id, Theme.status == "open")
        .order_by(ThemeWeeklyStat.week_start)
    ):
        weeks_by_theme.setdefault(theme_id, []).append(WeekCount(week_start, item_count))

    if not weeks_by_theme:
        return []
    themes = {
        theme.id: theme
        for theme in session.scalars(select(Theme).where(Theme.id.in_(weeks_by_theme)))
    }

    rising = []
    for theme_id, weeks in weeks_by_theme.items():
        series = fill_missing_weeks(
            [week for week in weeks if week.week_start <= latest_week], weeks=COMPARISON_WEEKS + 1
        )
        if not series or series[-1].week_start != latest_week:
            continue  # this theme had nothing in the newest week
        item_count = series[-1].item_count
        earlier = [week.item_count for week in series[:-1]]
        baseline = max(sum(earlier) / len(earlier) if earlier else 0.0, MIN_BASELINE)
        ratio = item_count / baseline
        if item_count >= items_threshold and ratio >= ratio_threshold:
            rising.append(RisingTheme(themes[theme_id], latest_week, item_count, baseline, ratio))

    return sorted(rising, key=lambda found: found.ratio, reverse=True)


def record_alerts(session: Session, workspace_id: int, rising: list[RisingTheme]) -> list[Alert]:
    """Save an alert for each rising theme, skipping ones already raised that week."""
    created = []
    for found in rising:
        statement = (
            insert(Alert)
            .values(
                workspace_id=workspace_id,
                theme_id=found.theme.id,
                week_start=found.week_start,
                item_count=found.item_count,
                baseline=found.baseline,
                ratio=found.ratio,
            )
            .on_conflict_do_nothing(index_elements=[Alert.theme_id, Alert.week_start])
            .returning(Alert.id)
        )
        alert_id = session.scalar(statement)
        if alert_id is not None:
            created.append(session.get(Alert, alert_id))
    session.commit()
    return [alert for alert in created if alert is not None]
