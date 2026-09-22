"""Turning feedback text into vectors, so similar reports can be grouped.

Two providers produce the same vector size, so they can be swapped without touching the
database: a small model running on this machine, or Gemini's embedding API.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings, get_settings
from app.errors import PermanentJobError

# Both providers are configured to produce this many numbers per item.
EMBEDDING_DIMENSIONS = 384


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    input_tokens: int
    latency_ms: int


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        """Return one vector per text, in the same order."""
        ...


def get_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()

    if settings.embedding_provider == "local":
        # Imported here because the package is an optional extra.
        from app.ai.local_embedder import LocalEmbedder

        return LocalEmbedder(settings.local_embedding_model)

    if not settings.gemini_api_key:
        raise PermanentJobError(
            "GEMINI_API_KEY is not set. Add it to .env, or set EMBEDDING_PROVIDER=local."
        )
    from app.ai.gemini import GeminiEmbedder

    return GeminiEmbedder(
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
        requests_per_minute=settings.gemini_requests_per_minute,
    )


def check_dimensions(vectors: Sequence[Sequence[float]], model: str) -> None:
    for vector in vectors:
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise PermanentJobError(
                f"Model {model} returned {len(vector)} numbers per item, "
                f"but the database stores {EMBEDDING_DIMENSIONS}."
            )
