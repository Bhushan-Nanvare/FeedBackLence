from collections.abc import Callable

from sqlalchemy.orm import Session

from app.maintenance import reclean_items
from app.models import FeedbackItem, Workspace

MakeItem = Callable[..., FeedbackItem]

NOISY = "The debugger stops at the wrong line.\n\nVersion: 1.122.1\nSandboxed: No"
CLEANED = "The debugger stops at the wrong line."


def test_recleaning_updates_text_and_fingerprint(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    item = make_item(1, body=NOISY)
    # Pretend it was imported under older cleaning rules.
    item.body_clean = NOISY
    db.commit()
    old_hash = item.content_hash

    stats = reclean_items(db, workspace.id)

    assert (stats.checked, stats.changed) == (1, 1)
    assert stats.characters_removed > 0
    db.expire_all()
    assert item.body_clean == CLEANED
    assert item.content_hash != old_hash


def test_a_dry_run_changes_nothing(db: Session, workspace: Workspace, make_item: MakeItem) -> None:
    item = make_item(1, body=NOISY)
    item.body_clean = NOISY
    db.commit()

    stats = reclean_items(db, workspace.id, dry_run=True)

    assert stats.changed == 1
    db.expire_all()
    assert item.body_clean == NOISY


def test_already_clean_items_are_left_alone(
    db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    make_item(1, body="Plain text with nothing to strip.")

    stats = reclean_items(db, workspace.id)

    assert (stats.checked, stats.changed) == (1, 0)
