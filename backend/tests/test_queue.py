from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.jobs import queue
from app.models import Job


def test_claim_marks_the_job_running_and_is_exclusive(db: Session) -> None:
    job = queue.enqueue(db, "demo", {"n": 1})
    db.commit()

    claimed = queue.claim_next(db)

    assert claimed is not None and claimed.id == job.id
    assert (claimed.status, claimed.attempts) == ("running", 1)
    assert claimed.locked_at is not None
    assert queue.claim_next(db) is None


def test_claim_skips_jobs_scheduled_for_later(db: Session) -> None:
    job = queue.enqueue(db, "demo", {})
    job.run_after = func.now() + timedelta(minutes=5)
    db.commit()

    assert queue.claim_next(db) is None


def test_failed_job_retries_with_backoff_then_gives_up(db: Session) -> None:
    job = queue.enqueue(db, "demo", {})
    job.max_attempts = 2
    db.commit()

    claimed = queue.claim_next(db)
    assert claimed is not None
    queue.mark_failed(db, claimed, "boom")

    assert (claimed.status, claimed.last_error) == ("queued", "boom")
    assert claimed.run_after > db.scalar(select(func.clock_timestamp())) + timedelta(seconds=20)

    db.execute(update(Job).where(Job.id == job.id).values(run_after=func.now()))
    db.commit()
    claimed = queue.claim_next(db)
    assert claimed is not None
    queue.mark_failed(db, claimed, "boom again")

    assert (claimed.status, claimed.attempts) == ("failed", 2)


def test_postpone_does_not_use_up_an_attempt(db: Session) -> None:
    queue.enqueue(db, "demo", {})
    db.commit()
    claimed = queue.claim_next(db)
    assert claimed is not None

    until = db.scalar(select(func.now())) + timedelta(hours=1)
    queue.postpone(db, claimed, until=until, reason="rate limited")

    assert (claimed.status, claimed.attempts, claimed.run_after) == ("queued", 0, until)
    assert queue.claim_next(db) is None


def test_job_abandoned_by_a_crashed_worker_is_reclaimed(db: Session) -> None:
    job = queue.enqueue(db, "demo", {})
    db.commit()
    queue.claim_next(db)
    db.execute(
        update(Job).where(Job.id == job.id).values(locked_at=func.now() - timedelta(minutes=20))
    )
    db.commit()

    reclaimed = queue.claim_next(db)

    assert reclaimed is not None and reclaimed.attempts == 2


def test_concurrent_workers_claim_different_jobs(db: Session) -> None:
    first = queue.enqueue(db, "demo", {"n": 1})
    second = queue.enqueue(db, "demo", {"n": 2})
    db.commit()

    with SessionLocal() as worker_a, SessionLocal() as worker_b:
        # Worker A holds a row lock on the first job, as it would mid-claim.
        worker_a.scalars(select(Job).where(Job.id == first.id).with_for_update()).one()

        claimed = queue.claim_next(worker_b)

        assert claimed is not None and claimed.id == second.id
        worker_a.rollback()


def test_find_active_matches_kind_status_and_payload(db: Session) -> None:
    job = queue.enqueue(db, "github_sync", {"source_id": 1})
    db.commit()

    found = queue.find_active(db, "github_sync", {"source_id": 1})
    assert found is not None and found.id == job.id
    assert queue.find_active(db, "github_sync", {"source_id": 2}) is None

    queue.mark_done(db, job)
    assert queue.find_active(db, "github_sync", {"source_id": 1}) is None
