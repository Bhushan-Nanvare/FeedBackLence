from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import PermanentJobError, RateLimitedError
from app.jobs import queue
from app.models import Job
from app.worker import run_next_job


def stored_job(db: Session, job_id: int) -> Job:
    db.expire_all()
    job = db.get(Job, job_id)
    assert job is not None
    return job


def test_returns_false_when_no_job_is_ready(db: Session) -> None:
    assert run_next_job({}) is False


def test_successful_job_is_marked_done(db: Session) -> None:
    job = queue.enqueue(db, "echo", {"value": 42})
    db.commit()
    seen: list[dict[str, Any]] = []

    assert run_next_job({"echo": lambda session, payload: seen.append(payload)}) is True

    assert seen == [{"value": 42}]
    assert stored_job(db, job.id).status == "done"


def test_crashing_job_is_queued_for_retry(db: Session) -> None:
    def explode(session: Session, payload: dict[str, Any]) -> None:
        raise ValueError("bad data")

    job = queue.enqueue(db, "explode", {})
    db.commit()

    run_next_job({"explode": explode})

    stored = stored_job(db, job.id)
    assert (stored.status, stored.attempts) == ("queued", 1)
    assert stored.last_error is not None and "bad data" in stored.last_error


def test_rate_limited_job_is_postponed_without_using_an_attempt(db: Session) -> None:
    reset_at = db.scalar(select(func.now())) + timedelta(minutes=30)

    def limited(session: Session, payload: dict[str, Any]) -> None:
        raise RateLimitedError("Test API", reset_at)

    job = queue.enqueue(db, "limited", {})
    db.commit()

    run_next_job({"limited": limited})

    stored = stored_job(db, job.id)
    assert (stored.status, stored.attempts, stored.run_after) == ("queued", 0, reset_at)


def test_permanent_error_fails_the_job_without_retry(db: Session) -> None:
    def misconfigured(session: Session, payload: dict[str, Any]) -> None:
        raise PermanentJobError("API key missing")

    job = queue.enqueue(db, "misconfigured", {})
    db.commit()

    run_next_job({"misconfigured": misconfigured})

    stored = stored_job(db, job.id)
    assert (stored.status, stored.attempts, stored.last_error) == ("failed", 1, "API key missing")


def test_unknown_job_kind_fails_without_retry(db: Session) -> None:
    job = queue.enqueue(db, "mystery", {})
    db.commit()

    run_next_job({})

    assert stored_job(db, job.id).status == "failed"
