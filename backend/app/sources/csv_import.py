"""Import feedback from a CSV file, such as an export from a support tool.

Spreadsheets vary, so common column names are recognised and anything else is ignored. A row
that cannot be used is reported back rather than silently dropped.
"""

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.embedding import request_embedding
from app.ai.tagging import request_tagging
from app.models import FeedbackItem, Source, Workspace
from app.processing.clean import clean_body
from app.processing.hashing import author_hash, content_hash
from app.processing.privacy import scrub_personal_data

logger = logging.getLogger(__name__)

MAX_ROWS = 5000
MAX_TITLE_CHARS = 200
MAX_PROBLEMS_REPORTED = 10

TEXT_COLUMNS = ("text", "body", "description", "feedback", "comment", "message", "content")
TITLE_COLUMNS = ("title", "subject", "summary", "headline")
DATE_COLUMNS = ("createdat", "date", "created", "timestamp", "submittedat", "receivedat")
URL_COLUMNS = ("url", "link", "permalink")
ID_COLUMNS = ("id", "externalid", "ticketid", "reference", "key")
AUTHOR_COLUMNS = ("author", "user", "email", "name", "reporter", "customer")

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S")


@dataclass
class ImportStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    problems: list[str] = field(default_factory=list)


def import_csv(
    session: Session, workspace: Workspace, *, filename: str, content: str
) -> tuple[Source, ImportStats]:
    """Read a CSV file into the workspace, then queue tagging and grouping."""
    stats = ImportStats()
    rows = list(csv.DictReader(io.StringIO(content)))
    if not rows:
        stats.problems.append("The file has no rows.")
        return _source_for(session, workspace, filename), stats

    columns = _match_columns(rows[0].keys())
    if columns["text"] is None:
        stats.problems.append(
            "No text column found. Name a column one of: " + ", ".join(TEXT_COLUMNS) + "."
        )
        return _source_for(session, workspace, filename), stats

    source = _source_for(session, workspace, filename)
    imported_at = datetime.now(UTC)
    values = []
    for number, row in enumerate(rows[:MAX_ROWS], start=2):  # row 1 is the header
        built = _row_values(row, columns, source, number, imported_at, stats)
        if built is not None:
            values.append(built)

    if len(rows) > MAX_ROWS:
        stats.problems.append(f"Only the first {MAX_ROWS} rows were read.")
    if values:
        _save(session, source, values, stats)
        request_tagging(session, workspace.id)
        request_embedding(session, workspace.id)
    session.commit()
    return source, stats


def _match_columns(headers: object) -> dict[str, str | None]:
    """Find which column holds what, ignoring case, spaces and underscores."""
    known = {_normalise(header): header for header in headers if header}
    return {
        "text": _first_match(known, TEXT_COLUMNS),
        "title": _first_match(known, TITLE_COLUMNS),
        "date": _first_match(known, DATE_COLUMNS),
        "url": _first_match(known, URL_COLUMNS),
        "id": _first_match(known, ID_COLUMNS),
        "author": _first_match(known, AUTHOR_COLUMNS),
    }


def _normalise(header: str) -> str:
    return "".join(character for character in header.lower() if character.isalnum())


def _first_match(known: dict[str, str], wanted: tuple[str, ...]) -> str | None:
    for name in wanted:
        if name in known:
            return known[name]
    return None


def _row_values(
    row: dict[str, str],
    columns: dict[str, str | None],
    source: Source,
    number: int,
    imported_at: datetime,
    stats: ImportStats,
) -> dict[str, object] | None:
    text = scrub_personal_data((row.get(columns["text"] or "") or "").strip())
    if not text:
        stats.skipped += 1
        if len(stats.problems) < MAX_PROBLEMS_REPORTED:
            stats.problems.append(f"Row {number} has no text.")
        return None

    title = scrub_personal_data((row.get(columns["title"] or "") or "").strip())
    if not title:
        title = text.split("\n", 1)[0][:MAX_TITLE_CHARS]
    created_at = _parse_date(row.get(columns["date"] or "")) or imported_at
    body_clean = clean_body(text)
    external_id = (row.get(columns["id"] or "") or "").strip() or _fingerprint(title, text)

    return {
        "workspace_id": source.workspace_id,
        "source_id": source.id,
        "external_id": external_id[:100],
        "url": (row.get(columns["url"] or "") or "").strip(),
        "title": title[:MAX_TITLE_CHARS],
        "body_raw": text,
        "body_clean": body_clean,
        "content_hash": content_hash(title, body_clean),
        "author_hash": author_hash("csv", (row.get(columns["author"] or "") or "").strip()),
        "author_is_maintainer": False,
        "state": "open",
        "state_reason": None,
        "labels": [],
        "comments_count": 0,
        "reactions_count": 0,
        "external_created_at": created_at,
        "external_updated_at": created_at,
    }


def _parse_date(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for pattern in DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _fingerprint(title: str, text: str) -> str:
    """A stable id for rows without one, so re-importing the same file does not duplicate."""
    return hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:32]


def _save(
    session: Session, source: Source, values: list[dict[str, object]], stats: ImportStats
) -> None:
    known_hashes = dict(
        session.execute(
            select(FeedbackItem.external_id, FeedbackItem.content_hash).where(
                FeedbackItem.source_id == source.id,
                FeedbackItem.external_id.in_([row["external_id"] for row in values]),
            )
        )
        .tuples()
        .all()
    )
    for row in values:
        previous = known_hashes.get(str(row["external_id"]))
        if previous is None:
            stats.created += 1
        elif previous != row["content_hash"]:
            stats.updated += 1
        else:
            stats.unchanged += 1

    statement = insert(FeedbackItem).values(values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[FeedbackItem.source_id, FeedbackItem.external_id],
            set_={
                column: statement.excluded[column]
                for column in ("url", "title", "body_raw", "body_clean", "content_hash")
            }
            | {"updated_at": func.now()},
        )
    )


def _source_for(session: Session, workspace: Workspace, filename: str) -> Source:
    name = filename.strip() or "upload.csv"
    source = session.scalar(
        select(Source).where(
            Source.workspace_id == workspace.id, Source.kind == "csv", Source.name == name
        )
    )
    if source is None:
        source = Source(workspace_id=workspace.id, kind="csv", name=name, config={})
        session.add(source)
        session.flush()
    source.last_synced_at = datetime.now(UTC)
    return source
