from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file lives at the repository root, shared with docker-compose.
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://feedbacklens:feedbacklens@localhost:5434/feedbacklens"
    cors_origins: list[str] = ["http://localhost:3000"]
    # Optional: without a token GitHub allows 60 requests/hour, with one 5,000.
    github_token: str | None = None
    worker_poll_interval_seconds: float = 2.0

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    # Free-tier limits differ per account (see AI Studio); stay under yours to avoid 429s.
    gemini_requests_per_minute: int = 10
    tagging_batch_size: int = 15
    tagging_max_items_per_job: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
