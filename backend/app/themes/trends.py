"""How fast a theme is growing, from its weekly counts."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

# How many weeks of history the dashboard shows.
RECENT_WEEKS = 8
# How many earlier weeks the latest week is compared against.
COMPARISON_WEEKS = 4


@dataclass(frozen=True)
class WeekCount:
    week_start: date
    item_count: int


def fill_missing_weeks(
    counts: Sequence[WeekCount], *, weeks: int = RECENT_WEEKS
) -> list[WeekCount]:
    """Return the last `weeks` weeks in order, with 0 for weeks that had no reports."""
    if not counts:
        return []
    by_week = {count.week_start: count.item_count for count in counts}
    last_week = max(by_week)
    series = []
    for index in range(weeks - 1, -1, -1):
        week_start = last_week - index * timedelta(weeks=1)
        series.append(WeekCount(week_start, by_week.get(week_start, 0)))
    return series


def growth_ratio(
    counts: Sequence[WeekCount], *, comparison_weeks: int = COMPARISON_WEEKS
) -> float | None:
    """The latest week compared with the average of the weeks before it.

    2.0 means twice as many reports as usual. None means there is no useful comparison yet.
    """
    series = fill_missing_weeks(counts, weeks=comparison_weeks + 1)
    if len(series) < 2:
        return None
    latest = series[-1].item_count
    earlier = [week.item_count for week in series[:-1]]
    baseline = sum(earlier) / len(earlier)
    if baseline == 0:
        return None
    return latest / baseline
