"""Local, offline, deterministic embeddings (AMENDMENTS A5).

``bge-small-en-v1.5`` via fastembed: ONNX on CPU, ~130 MB, no key, no network at
run time. A5 rejects a hosted API for a reason that matters more than cost —
the dedupe fixture suite has to be reproducible, and a remote model that is
silently retrained makes it not.

The model is fetched once by ``make model`` (called from ``make setup``) into a
cache directory outside the repository. Nothing here reaches the network during
a test or a request, and ``OUTBOUND_HTTP_ENABLED`` is not consulted because this
module never touches httpx — the kill switch governs *source* fetches, and
conflating the two would make it ambiguous which one a reader had disabled.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

# A5 fixes both. They are stored on every job_embeddings row so that replacing
# the model is a backfill rather than a mystery.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384


def cache_dir() -> Path:
    """Where the ONNX weights live. Outside the repository, deliberately.

    A 130 MB binary inside the tree would end up in a commit eventually, and
    ``git`` is not an artefact store.
    """
    override = os.environ.get("FASTEMBED_CACHE_PATH")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "nightshift" / "fastembed"


def real_model_available() -> bool:
    """True when the model has been downloaded.

    Used to skip the real-model tests rather than fail them. A suite that
    cannot run without a 130 MB download is a suite people stop running; one
    that silently passes without it is worse. A skip says which it is.
    """
    directory = cache_dir()
    if not directory.exists():
        return False
    return any(directory.rglob("*.onnx"))


class Embedder(Protocol):
    """Anything that turns text into vectors of ``EMBEDDING_DIMENSION`` floats."""

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


class FastEmbedEmbedder:
    """The real model. Loaded lazily, because constructing it costs seconds."""

    def __init__(self) -> None:
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            log.info("embedding_model_loading", model=EMBEDDING_MODEL_NAME)
            self._model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=str(cache_dir()))
        return self._model

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        model = self._load()
        return [tuple(float(value) for value in vector) for vector in model.embed(list(texts))]


class StubEmbedder:
    """A deterministic test double. **Not** the product (invariant I7).

    Hashes character trigrams into a fixed-width vector. That is not semantic
    similarity, but it is directionally right — texts sharing many trigrams
    score higher than texts sharing few — which is enough for tests whose
    subject is the *plumbing* around embeddings rather than their quality.

    Anything asserting a quality claim, including every labelled dedupe pair
    that reaches the similarity layer, uses the real model and is skipped when
    it is absent. A verdict assertion that passed under this class would be
    evidence of nothing.
    """

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            buckets = [0.0] * EMBEDDING_DIMENSION
            cleaned = " ".join((text or "").lower().split())
            for index in range(max(len(cleaned) - 2, 0)):
                trigram = cleaned[index : index + 3]
                digest = hashlib.sha256(trigram.encode()).digest()
                buckets[int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION] += 1.0
            norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
            vectors.append(tuple(value / norm for value in buckets))
        return vectors


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, with a zero vector scoring 0 rather than NaN.

    NaN compares false against every threshold, so an empty description would
    silently switch off the similarity layer with nothing reporting it.
    """
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@lru_cache(maxsize=1)
def default_embedder() -> Embedder:
    """One process-wide model instance. Loading it per call would dominate."""
    return FastEmbedEmbedder()
