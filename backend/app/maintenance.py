"""Maintenance commands: `python -m app.maintenance reclean --workspace demo`.

`reclean`: cleaning rules improve over time. Already-imported reports keep the text they
were cleaned with, so this re-cleans them from the original. Items whose text changes get
a new fingerprint, which makes the worker tag and embed them again on its next run.

`grant`: gives an account a role in a workspace. A workspace that nobody owns — the demo
one on a fresh database, say — cannot be managed from the web app, and this is the way in.
"""

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import WORKSPACE_ROLES, FeedbackItem, Membership, User, Workspace
from app.processing.clean import clean_body
from app.processing.hashing import content_hash


@dataclass
class RecleanStats:
    checked: int = 0
    changed: int = 0
    characters_removed: int = 0


def reclean_items(session: Session, workspace_id: int, *, dry_run: bool = False) -> RecleanStats:
    stats = RecleanStats()
    items = session.scalars(select(FeedbackItem).where(FeedbackItem.workspace_id == workspace_id))
    for item in items:
        stats.checked += 1
        cleaned = clean_body(item.body_raw)
        if cleaned == item.body_clean:
            continue
        stats.changed += 1
        stats.characters_removed += len(item.body_clean) - len(cleaned)
        if not dry_run:
            item.body_clean = cleaned
            item.content_hash = content_hash(item.title, cleaned)

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return stats


def grant_role(session: Session, workspace: Workspace, email: str, role: str) -> str:
    """Give the account that email belongs to this role. Returns what changed."""
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise LookupError(f"Nobody is registered as '{email}'. Sign up first, then run this.")

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace.id, Membership.user_id == user.id
        )
    )
    if membership is None:
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=role))
        outcome = f"{user.email} is now {role} of {workspace.slug}."
    elif membership.role == role:
        outcome = f"{user.email} was already {role} of {workspace.slug}."
    else:
        was, membership.role = membership.role, role
        outcome = f"{user.email} changed from {was} to {role} of {workspace.slug}."
    session.commit()
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.maintenance", description="Housekeeping for imported feedback."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    reclean = commands.add_parser("reclean", help="re-clean stored reports with today's rules")
    reclean.add_argument("--workspace", default="demo", help="workspace slug (default: demo)")
    reclean.add_argument(
        "--dry-run", action="store_true", help="report what would change, without saving"
    )
    grant = commands.add_parser("grant", help="give a registered account a role in a workspace")
    grant.add_argument("--workspace", default="demo", help="workspace slug (default: demo)")
    grant.add_argument("--email", required=True, help="the account's email address")
    grant.add_argument("--role", default="owner", choices=WORKSPACE_ROLES)
    args = parser.parse_args()

    with SessionLocal() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == args.workspace))
        if workspace is None:
            print(f"No workspace named '{args.workspace}'.", file=sys.stderr)
            return 2

        if args.command == "grant":
            try:
                print(grant_role(session, workspace, args.email, args.role))
            except LookupError as exc:
                print(exc, file=sys.stderr)
                return 2
            return 0

        stats = reclean_items(session, workspace.id, dry_run=args.dry_run)

    print(
        f"Checked {stats.checked} reports, {stats.changed} changed, "
        f"{stats.characters_removed} characters of noise removed."
        + (" (dry run, nothing saved)" if args.dry_run else "")
    )
    if stats.changed and not args.dry_run:
        print("Run the worker to tag and embed the changed reports again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
