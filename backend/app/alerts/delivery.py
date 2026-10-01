"""Send alerts about rising themes. Nothing leaves the machine unless a channel is set up."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Alert, Theme

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 10.0


@dataclass
class DeliveryStats:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class AlertSender(Protocol):
    channel: str

    def send(self, message: str) -> None: ...


class SlackSender:
    channel = "slack"

    def __init__(self, webhook_url: str, client: Any | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx

    def send(self, message: str) -> None:
        response = self._client.post(
            self._webhook_url, json={"text": message}, timeout=SEND_TIMEOUT_SECONDS
        )
        response.raise_for_status()


def get_sender(settings: Settings | None = None) -> AlertSender | None:
    """The configured channel, or None when alerts should only be recorded."""
    settings = settings or get_settings()
    if settings.slack_webhook_url:
        return SlackSender(settings.slack_webhook_url)
    return None


def send_pending_alerts(
    session: Session, workspace_id: int, sender: AlertSender | None
) -> DeliveryStats:
    pending = list(
        session.scalars(
            select(Alert)
            .where(Alert.workspace_id == workspace_id, Alert.status == "pending")
            .order_by(Alert.id)
        )
    )
    stats = DeliveryStats()
    if not pending:
        return stats

    themes = {
        theme.id: theme
        for theme in session.scalars(
            select(Theme).where(Theme.id.in_([alert.theme_id for alert in pending]))
        )
    }

    for alert in pending:
        theme = themes.get(alert.theme_id)
        if sender is None or theme is None:
            # Recorded, so the dashboard can show it, but nothing is sent anywhere.
            alert.status = "skipped"
            alert.channel = "none"
            stats.skipped += 1
            continue
        try:
            sender.send(build_message(alert, theme))
        except Exception as exc:
            logger.warning("alert %s could not be sent: %s", alert.id, exc)
            alert.status = "failed"
            alert.channel = sender.channel
            alert.error = str(exc)[:2000]
            stats.failed += 1
        else:
            alert.status = "sent"
            alert.channel = sender.channel
            alert.sent_at = datetime.now(UTC)
            alert.error = None
            stats.sent += 1

    session.commit()
    return stats


def build_message(alert: Alert, theme: Theme, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    reports = "report" if alert.item_count == 1 else "reports"
    message = (
        f"Rising feedback: {theme.name}\n"
        f"{alert.item_count} {reports} in the week of {alert.week_start.isoformat()}, "
        f"{alert.ratio:.1f}x the usual {alert.baseline:.1f} a week."
    )
    if settings.public_web_url:
        base = settings.public_web_url.rstrip("/")
        message += f"\n{base}/workspaces/demo/themes/{theme.id}"
    return message
