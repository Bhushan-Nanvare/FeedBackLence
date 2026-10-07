from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # "local" runs a small model on this machine (no key, no quota); "gemini" calls the API.
    embedding_provider: Literal["local", "gemini"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_batch_size: int = 32
    embedding_max_items_per_job: int = 1000

    # Fewer reports than this stay unsorted instead of becoming a theme.
    cluster_min_size: int = 5
    # How crowded a neighbourhood must be to start a theme. Lower groups more, but looser.
    cluster_min_samples: int = 2
    # Vectors are squeezed to this many dimensions before grouping, which finds far more
    # groups at almost the same tightness (measured on VS Code issues: 43% vs 13% grouped).
    cluster_pca_dimensions: int = 50
    # A group whose members sit further than this from its centre is scattered rather than
    # a real theme, so its items stay unsorted instead of forming a "miscellaneous" group.
    cluster_min_coherence: float = 0.6
    # How much of the smaller side a new cluster and an old theme must share to count as
    # the same theme. Comparing against the smaller side matters because themes grow by
    # attaching leftover reports, so the stored theme is bigger than the cluster it came from.
    theme_match_min_overlap: float = 0.5
    # How close a leftover item must be to a theme's centre to join it.
    theme_assign_min_similarity: float = 0.8

    # A theme is "rising" when its latest week is this many times the usual rate...
    alert_min_ratio: float = 3.0
    # ...and has at least this many reports, so 1 → 3 doesn't count as tripling.
    alert_min_items: int = 8
    # Where alerts go. Without this, they are recorded but not sent anywhere.
    slack_webhook_url: str | None = None
    # Used to link to a theme from an alert, when the app is reachable somewhere.
    public_web_url: str | None = None

    # The repository tickets are filed into, e.g. "my-name/my-repo". Must be yours.
    ticket_repo: str | None = None
    # Filing into a repository you only import from would spam someone else's project.
    allow_filing_to_source_repo: bool = False
    # How alike two issue titles must be to be called a possible duplicate.
    ticket_duplicate_min_similarity: float = 0.8
    # How many recent issues in the target repository to compare against.
    ticket_duplicate_candidates: int = 100
    ticket_quotes: int = 5

    # Signs sign-in tokens. Without it a temporary one is used, so restarting the API signs
    # everyone out: fine locally, not fine once deployed.
    auth_secret_key: str | None = None
    auth_token_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
