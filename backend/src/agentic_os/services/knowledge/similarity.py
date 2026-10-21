"""How close two documents are (phase 15): the cosine of their centroids.

Raw cosines are not comparable between models (spike S1: the «same topic» mean is 0.91 for e5,
0.82 for EmbeddingGemma and 0.68 for bge-m3). Subtracting the mean vector of the library first
puts all of them on one scale, where 0.20 separates «related» and 0.80 «the same text again».
With only a few documents there is no reliable mean, so the raw cosine is used with a threshold
of its own.
"""

from __future__ import annotations

import numpy as np

MIN_FOR_CENTERING = 8  # documents with a vector needed to trust the library's mean
RELATED = 0.20  # centered cosine: a link between two documents
NEAREST_FLOOR = 0.10  # a document's closest neighbour is linked at least from here
DUPLICATE = 0.80  # centered cosine: the same content in other words
DUPLICATE_RAW = 0.97  # raw cosine, for a library too small to center


def normalized(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def centroid_of(vectors: np.ndarray) -> np.ndarray:
    """The document as one point: the mean of its chunks' vectors, normalised."""
    return normalized(vectors.mean(axis=0))


def center(matrix: np.ndarray, mean: np.ndarray) -> np.ndarray:
    """The rows minus the library's mean, each normalised again."""
    shifted = matrix - mean
    norms = np.linalg.norm(shifted, axis=1, keepdims=True)
    return shifted / np.maximum(norms, 1e-12)


def similarities(candidate: np.ndarray, library: np.ndarray) -> tuple[np.ndarray, bool]:
    """(cosine of `candidate` with every row of `library`, whether it was centered). The mean is
    that of the library plus the candidate, so a candidate alone in a small library does not
    cancel itself out."""
    if len(library) == 0:
        return np.zeros(0, dtype=np.float32), False
    if len(library) + 1 < MIN_FOR_CENTERING:
        return library @ candidate, False
    mean = np.vstack([library, candidate[None, :]]).mean(axis=0)
    return center(library, mean) @ center(candidate[None, :], mean)[0], True


def is_duplicate(score: float, centered: bool) -> bool:
    return score >= (DUPLICATE if centered else DUPLICATE_RAW)
