"""Build and update the checked set of labels used to score tagging."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.evals.label_map import expected_area, expected_type
from app.models import EvalLabel, FeedbackItem

DEFAULT_DRAFT_LIMIT = 200


@dataclass
class DraftStats:
    created: int = 0
    updated: int = 0
    no_usable_labels: int = 0


def build_draft_labels(
    session: Session, workspace_id: int, *, limit: int = DEFAULT_DRAFT_LIMIT
) -> DraftStats:
    """Create draft labels from the source's own labels, newest items first.

    Labels a person has checked are left alone.
    """
    checked_by_people = select(EvalLabel.item_id).where(EvalLabel.source == "human")
    items = session.scalars(
        select(FeedbackItem)
        .where(
            FeedbackItem.workspace_id == workspace_id,
            FeedbackItem.author_is_maintainer.is_(False),
            FeedbackItem.labels != [],
            FeedbackItem.id.not_in(checked_by_people),
        )
        .order_by(FeedbackItem.external_created_at.desc(), FeedbackItem.id)
        .limit(limit)
    )

    stats = DraftStats()
    for item in items:
        item_type = expected_type(item.labels)
        item_area = expected_area(item.labels)
        if item_type is None and item_area is None:
            stats.no_usable_labels += 1
            continue
        existed = session.scalar(
            select(func.count()).select_from(EvalLabel).where(EvalLabel.item_id == item.id)
        )
        _upsert_label(
            session,
            item_id=item.id,
            workspace_id=workspace_id,
            expected_type=item_type,
            expected_area=item_area,
            source="github_label",
        )
        if existed:
            stats.updated += 1
        else:
            stats.created += 1

    session.commit()
    return stats


def record_checked_label(
    session: Session,
    *,
    item_id: int,
    workspace_id: int,
    expected_type: str | None,
    expected_area: str | None,
) -> None:
    """Save a person's correction as the checked answer, keeping fields they didn't change."""
    _upsert_label(
        session,
        item_id=item_id,
        workspace_id=workspace_id,
        expected_type=expected_type,
        expected_area=expected_area,
        source="human",
    )


def _upsert_label(
    session: Session,
    *,
    item_id: int,
    workspace_id: int,
    expected_type: str | None,
    expected_area: str | None,
    source: str,
) -> None:
    statement = insert(EvalLabel).values(
        item_id=item_id,
        workspace_id=workspace_id,
        expected_type=expected_type,
        expected_area=expected_area,
        source=source,
    )
    keep_existing = {
        "expected_type": func.coalesce(statement.excluded.expected_type, EvalLabel.expected_type),
        "expected_area": func.coalesce(statement.excluded.expected_area, EvalLabel.expected_area),
        "source": statement.excluded.source,
        "updated_at": func.now(),
    }
    # A draft never overwrites an answer a person checked.
    where = None if source == "human" else EvalLabel.source != "human"
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[EvalLabel.item_id], set_=keep_existing, where=where
        )
    )
