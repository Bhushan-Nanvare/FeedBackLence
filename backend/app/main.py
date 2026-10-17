from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import (
    alerts,
    ask,
    auth,
    items,
    jobs,
    search,
    sources,
    tagging,
    themes,
    tickets,
    usage,
    widget,
    workspaces,
)
from app.api.deps import SessionDep
from app.config import get_settings

app = FastAPI(title="FeedbackLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(sources.router)
app.include_router(jobs.router)
app.include_router(tagging.router)
app.include_router(items.router)
app.include_router(themes.router)
app.include_router(search.router)
app.include_router(ask.router)
app.include_router(alerts.router)
app.include_router(tickets.router)
app.include_router(usage.router)
app.include_router(widget.router)

# Serve the embeddable widget JS from /static/widget.js.  The static
# directory lives next to this file at app/static/.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


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
