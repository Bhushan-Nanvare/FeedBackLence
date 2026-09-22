"""Background worker. Run with `python -m app.worker` (add --once to exit when idle)."""

import argparse
import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.ai.embedding import EMBED_ITEMS_JOB, run_embed_items_job
from app.ai.tagging import TAG_ITEMS_JOB, run_tag_items_job
from app.config import get_settings
from app.db import SessionLocal
from app.errors import PermanentJobError, RateLimitedError
from app.jobs import queue
from app.sources.github_sync import GITHUB_SYNC_JOB, run_github_sync_job
from app.themes.clustering import CLUSTER_ITEMS_JOB, run_cluster_items_job

logger = logging.getLogger("app.worker")

JobHandler = Callable[[Session, dict[str, Any]], None]

HANDLERS: dict[str, JobHandler] = {
    GITHUB_SYNC_JOB: run_github_sync_job,
    TAG_ITEMS_JOB: run_tag_items_job,
    EMBED_ITEMS_JOB: run_embed_items_job,
    CLUSTER_ITEMS_JOB: run_cluster_items_job,
}


def run_next_job(handlers: dict[str, JobHandler] = HANDLERS) -> bool:
    """Run one ready job. Returns False when no job was ready."""
    with SessionLocal() as session:
        job = queue.claim_next(session)
        if job is None:
            return False

        handler = handlers.get(job.kind)
        if handler is None:
            queue.mark_failed(session, job, f"no handler for job kind {job.kind!r}", retry=False)
            return True

        logger.info("job %s (%s) started, attempt %s", job.id, job.kind, job.attempts)
        try:
            handler(session, job.payload)
        except RateLimitedError as exc:
            session.rollback()
            logger.warning("job %s postponed: %s", job.id, exc)
            queue.postpone(session, job, until=exc.reset_at, reason=str(exc))
        except PermanentJobError as exc:
            session.rollback()
            logger.error("job %s failed permanently: %s", job.id, exc)
            queue.mark_failed(session, job, str(exc), retry=False)
        except Exception as exc:
            session.rollback()
            logger.exception("job %s failed", job.id)
            queue.mark_failed(session, job, repr(exc))
        else:
            queue.mark_done(session, job)
            logger.info("job %s done", job.id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FeedbackLens background jobs.")
    parser.add_argument(
        "--once", action="store_true", help="exit when no job is ready instead of waiting"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    poll_interval = get_settings().worker_poll_interval_seconds
    logger.info("worker started")
    try:
        while True:
            if run_next_job():
                continue
            if args.once:
                break
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
