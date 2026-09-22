"""Embeddings from a small model running on this machine: no API key, no quota, no cost."""

import time
from collections.abc import Sequence
from typing import Any

from app.ai.embeddings import EmbeddingResult, check_dimensions
from app.errors import PermanentJobError

INSTALL_HINT = (
    "Local embeddings need the optional package: run `uv sync --extra local-embeddings` "
    "in backend/, or set EMBEDDING_PROVIDER=gemini in .env."
)


class LocalEmbedder:
    def __init__(self, model: str, embedder: Any | None = None) -> None:
        self.model = model
        self._embedder = embedder if embedder is not None else _load(model)

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        started = time.monotonic()
        vectors = [vector.tolist() for vector in self._embedder.embed(list(texts))]
        check_dimensions(vectors, self.model)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            input_tokens=0,  # nothing is billed: the model runs here
            latency_ms=round((time.monotonic() - started) * 1000),
        )


def _load(model: str) -> Any:
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover - depends on how the env was installed
        raise PermanentJobError(INSTALL_HINT) from exc
    # Downloads the model once (about 130 MB), then reuses the local copy.
    return TextEmbedding(model_name=model)
