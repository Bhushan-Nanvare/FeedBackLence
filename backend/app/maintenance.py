"""Maintenance commands: `python -m app.maintenance reclean --workspace demo`.

Cleaning rules improve over time. Already-imported reports keep the text they were cleaned
with, so this re-cleans them from the original. Items whose text changes get a new
fingerprint, which makes the worker tag and embed them again on its next run.
"""

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FeedbackItem, Workspace
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
    args = parser.parse_args()

    with SessionLocal() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == args.workspace))
        if workspace is None:
            print(f"No workspace named '{args.workspace}'.", file=sys.stderr)
            return 2
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
