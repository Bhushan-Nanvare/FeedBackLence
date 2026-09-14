from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import jobs, sources
from app.api.deps import SessionDep
from app.config import get_settings

app = FastAPI(title="FeedbackLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sources.router)
app.include_router(jobs.router)


@app.get("/health")
def health(response: Response, session: SessionDep) -> dict[str, str | None]:
    try:
        pgvector_version = session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    except OperationalError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable", "pgvector": None}

    return {"status": "ok", "database": "ok", "pgvector": pgvector_version}
