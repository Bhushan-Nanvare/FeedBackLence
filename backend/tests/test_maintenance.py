from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.maintenance import grant_role, reclean_items
from app.models import FeedbackItem, Membership, User, Workspace

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


def test_granting_a_role_to_a_workspace_nobody_owns(
    db: Session, workspace: Workspace, owner: User
) -> None:
    """How a fresh database gets its first owner, since the web app cannot do it."""
    db.query(Membership).delete()
    db.commit()

    said = grant_role(db, workspace, "OWNER@example.com", "owner")

    assert "is now owner" in said
    role = db.scalar(select(Membership.role).where(Membership.user_id == owner.id))
    assert role == "owner"


def test_granting_changes_an_existing_role(db: Session, workspace: Workspace, owner: User) -> None:
    said = grant_role(db, workspace, owner.email, "viewer")

    assert "changed from owner to viewer" in said
    assert db.scalar(select(Membership.role).where(Membership.user_id == owner.id)) == "viewer"
    # Granting the same role twice is not an error.
    assert "already viewer" in grant_role(db, workspace, owner.email, "viewer")


def test_granting_to_an_unregistered_address_says_so(db: Session, workspace: Workspace) -> None:
    with pytest.raises(LookupError, match="Sign up first"):
        grant_role(db, workspace, "nobody@example.com", "owner")
