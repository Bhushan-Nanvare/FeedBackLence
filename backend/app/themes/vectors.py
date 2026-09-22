"""Small vector helpers shared by the theme code."""

from collections.abc import Sequence

import numpy as np


def unit_vectors(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    """Scale every vector to length 1, so a dot product is the cosine similarity."""
    array = np.asarray(vectors, dtype=np.float32)
    lengths = np.linalg.norm(array, axis=1, keepdims=True)
    return array / np.where(lengths == 0, 1, lengths)
