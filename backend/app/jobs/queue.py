"""A small job queue on top of Postgres.

Workers claim jobs with SELECT ... FOR UPDATE SKIP LOCKED, so several workers can run at once
without a separate broker such as Redis.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Job

# A running job whose worker hasn't finished in this long is assumed crashed and re-claimed.
STALE_LOCK_AFTER = timedelta(minutes=15)
BASE_RETRY_DELAY = timedelta(seconds=30)
MAX_RETRY_DELAY = timedelta(hours=1)
ACTIVE_STATUSES = ("queued", "running")


def enqueue(
    session: Session, kind: str, payload: dict[str, Any], *, workspace_id: int | None = None
) -> Job:
    """Add a job; the caller commits."""
    job = Job(kind=kind, payload=payload, workspace_id=workspace_id)
    session.add(job)
    session.flush()
    return job


def find_active(session: Session, kind: str, payload: dict[str, Any]) -> Job | None:
    """Return a queued or running job of this kind whose payload contains `payload`."""
    return session.scalars(
        select(Job)
        .where(Job.kind == kind, Job.status.in_(ACTIVE_STATUSES), Job.payload.contains(payload))
        .order_by(Job.id)
        .limit(1)
    ).first()


def claim_next(session: Session) -> Job | None:
    """Lock the next ready job (or one abandoned by a crashed worker) and mark it running."""
    now = func.now()
    job = session.scalars(
        select(Job)
        .where(
            or_(
                and_(Job.status == "queued", Job.run_after <= now),
                and_(Job.status == "running", Job.locked_at < now - STALE_LOCK_AFTER),
            )
        )
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()
    if job is None:
        session.commit()
        return None

    job.status = "running"
    job.locked_at = func.now()
    job.attempts += 1
    session.commit()
    return job


def mark_done(session: Session, job: Job) -> None:
    job.status = "done"
    job.locked_at = None
    job.last_error = None
    session.commit()


def mark_failed(session: Session, job: Job, error: str, *, retry: bool = True) -> None:
    """Record a failure; retry later with exponential backoff until attempts run out."""
    job.last_error = error[:2000]
    job.locked_at = None
    if retry and job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = func.now() + retry_delay(job.attempts)
    else:
        job.status = "failed"
    session.commit()


def postpone(session: Session, job: Job, *, until: datetime, reason: str) -> None:
    """Put a job back without using up an attempt, e.g. after hitting an API rate limit."""
    job.status = "queued"
    job.run_after = until
    job.attempts = max(job.attempts - 1, 0)
    job.locked_at = None
    job.last_error = reason
    session.commit()


def retry_delay(attempts: int) -> timedelta:
    return min(BASE_RETRY_DELAY * 2 ** max(attempts - 1, 0), MAX_RETRY_DELAY)
