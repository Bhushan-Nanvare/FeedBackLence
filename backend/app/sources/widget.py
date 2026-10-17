"""Accept feedback submitted by the embeddable widget.

The widget is a small JavaScript snippet that a website owner pastes into their
page.  When a visitor submits feedback, the snippet POSTs it here.  This module
handles the same pipeline as a CSV import — scrub PII, clean the text, create a
FeedbackItem, and queue tagging and embedding — but for a single item at a time.

Widget submissions are unauthenticated (the whole point is that external visitors
can send feedback), so we only accept them for workspaces that have a widget
source enabled.
"""

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embedding import request_embedding
from app.ai.tagging import request_tagging
from app.models import FeedbackItem, Source, Workspace
from app.processing.clean import clean_body
from app.processing.hashing import author_hash, content_hash
from app.processing.privacy import scrub_personal_data

logger = logging.getLogger(__name__)

# The maximum length of the title we derive from the submission text when
# the submitter does not provide one (which is always, since the widget
# form only has a text field).
MAX_TITLE_CHARS = 200


def get_or_create_widget_source(session: Session, workspace: Workspace) -> Source:
    """Find the widget source for a workspace, or create one if it does not exist.

    Each workspace has at most one widget source.  Creating it is idempotent:
    calling this twice returns the same row.
    """
    source = session.scalar(
        select(Source).where(
            Source.workspace_id == workspace.id,
            Source.kind == "widget",
        )
    )
    if source is None:
        source = Source(
            workspace_id=workspace.id,
            kind="widget",
            name="widget",
            config={},
        )
        session.add(source)
        session.flush()
        logger.info("created widget source %s for workspace %s", source.id, workspace.slug)
    return source


def submit_feedback(
    session: Session,
    workspace: Workspace,
    *,
    text: str,
    email: str | None = None,
    name: str | None = None,
) -> FeedbackItem:
    """Accept one piece of feedback from the widget and queue AI processing.

    Steps:
    1. Scrub PII (emails, phone numbers) from the text.
    2. Clean the text (remove markdown noise, templates, etc.).
    3. Create a FeedbackItem linked to the workspace's widget source.
    4. Queue tagging and embedding jobs so the worker picks them up.
    5. The caller is responsible for committing the session.
    """
    # -- 1. PII scrubbing: remove email addresses and phone numbers from the
    #    submitted text so they are never stored or sent to an AI model.
    scrubbed_text = scrub_personal_data(text)

    # -- 2. Derive a title from the first line of the submission, since the
    #    widget form only has a text field.  Truncate to a reasonable length.
    title = scrubbed_text.split("\n", 1)[0][:MAX_TITLE_CHARS]

    # -- 3. Clean the text using the same pipeline as GitHub issues and CSVs.
    body_clean = clean_body(scrubbed_text)

    # -- 4. Build a unique external_id from a hash of the text so that
    #    submitting the exact same feedback twice does not create duplicates.
    external_id = _fingerprint(title, scrubbed_text)

    # -- 5. Build a pseudonymous author hash from the email or name, or
    #    "anonymous" when neither is provided.  This is enough to count
    #    distinct submitters without storing who they are.
    author_identifier = (email or name or "anonymous").strip()
    hashed_author = author_hash("widget", author_identifier)

    # -- 6. Find or create the widget source for this workspace.
    source = get_or_create_widget_source(session, workspace)
    source.last_synced_at = datetime.now(UTC)

    now = datetime.now(UTC)

    # -- 7. Create the feedback item.
    item = FeedbackItem(
        workspace_id=workspace.id,
        source_id=source.id,
        external_id=external_id,
        url="",  # widget submissions do not have an external URL
        title=title,
        body_raw=scrubbed_text,
        body_clean=body_clean,
        content_hash=content_hash(title, body_clean),
        author_hash=hashed_author,
        author_is_maintainer=False,
        state="open",
        state_reason=None,
        labels=[],
        comments_count=0,
        reactions_count=0,
        external_created_at=now,
        external_updated_at=now,
    )
    session.add(item)
    session.flush()  # get the id before returning

    # -- 8. Queue tagging and embedding so the worker processes the new item.
    request_tagging(session, workspace.id)
    request_embedding(session, workspace.id)

    logger.info(
        "widget submission %s accepted for workspace %s (item %s)",
        external_id[:8],
        workspace.slug,
        item.id,
    )
    return item


def _fingerprint(title: str, text: str) -> str:
    """A stable id for widget submissions, so the same text twice does not duplicate."""
    return hashlib.sha256(f"widget:{title}\n{text}".encode()).hexdigest()[:32]
