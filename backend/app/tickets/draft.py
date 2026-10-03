"""Turn a theme into a ready-to-file issue, backed by the reports that justify it."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FeedbackItem, Source, Theme, ThemeItem, ThemeWeeklyStat
from app.themes.trends import WeekCount, growth_ratio

MAX_TITLE_CHARS = 120
MAX_QUOTE_CHARS = 180


@dataclass(frozen=True)
class DraftContent:
    title: str
    body: str


def build_draft(session: Session, theme: Theme, *, quotes: int | None = None) -> DraftContent:
    """Write the issue text: how many reports, how fast it is growing, and real examples."""
    settings = get_settings()
    examples = list(
        session.scalars(
            select(FeedbackItem)
            .join(ThemeItem, ThemeItem.item_id == FeedbackItem.id)
            .where(ThemeItem.theme_id == theme.id)
            .order_by(ThemeItem.similarity.desc())
            .limit(quotes if quotes is not None else settings.ticket_quotes)
        )
    )
    weeks = [
        WeekCount(stat.week_start, stat.item_count)
        for stat in session.scalars(
            select(ThemeWeeklyStat)
            .where(ThemeWeeklyStat.theme_id == theme.id)
            .order_by(ThemeWeeklyStat.week_start)
        )
    ]
    sources = sorted(
        set(
            session.scalars(
                select(Source.name)
                .join(FeedbackItem, FeedbackItem.source_id == Source.id)
                .join(ThemeItem, ThemeItem.item_id == FeedbackItem.id)
                .where(ThemeItem.theme_id == theme.id)
            )
        )
    )

    return DraftContent(
        title=theme.name.strip()[:MAX_TITLE_CHARS],
        body=_body(theme, examples, growth_ratio(weeks), sources),
    )


def _body(
    theme: Theme, examples: list[FeedbackItem], growth: float | None, sources: list[str]
) -> str:
    reports = "report" if theme.item_count == 1 else "reports"
    opening = f"**{theme.item_count} {reports}** are grouped under this."
    if theme.first_seen_at and theme.last_seen_at:
        opening += (
            f" First seen {theme.first_seen_at.date().isoformat()}, "
            f"latest {theme.last_seen_at.date().isoformat()}."
        )
    lines = [opening]
    if growth is not None:
        lines.append(f"The latest week is {growth:.1f}x the usual weekly rate.")
    if theme.summary:
        lines += ["", theme.summary]

    if examples:
        lines += ["", "### What people report", ""]
        for item in examples:
            when = item.external_created_at.date().isoformat()
            lines.append(f"- [{item.title[:MAX_QUOTE_CHARS]}]({item.url}) — {when}")
            quote = _quote(item)
            if quote:
                lines.append(f"  > {quote}")

    origin = ", ".join(sources) if sources else "imported feedback"
    lines += ["", "---", f"Grouped by FeedbackLens from {origin}."]
    return "\n".join(lines)


def _quote(item: FeedbackItem) -> str:
    """One readable line from a report: its summary if tagged, otherwise its own words."""
    text = item.tag.summary if item.tag and item.tag.summary else item.body_clean
    first_line = " ".join(text.split())
    if len(first_line) <= MAX_QUOTE_CHARS:
        return first_line
    return first_line[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0] + "…"
