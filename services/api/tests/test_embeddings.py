"""The local embedding model (AMENDMENTS A5).

Most of this file uses ``StubEmbedder``, because a unit test should not load a
130 MB ONNX model. Exactly one class exercises the real one, and it is the
class that keeps A5 honest: determinism is what makes the dedupe fixture suite
reproducible, and a stub asserting its own determinism proves nothing at all.
"""

from __future__ import annotations

import math

import pytest

from nightshift.domain.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    StubEmbedder,
    cosine_similarity,
    real_model_available,
)


def test_cosine_of_identical_vectors_is_one() -> None:
    vector = (0.1, 0.2, 0.3)
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


def test_cosine_of_a_zero_vector_is_zero_not_nan() -> None:
    """A zero vector divides by zero. NaN compares false against every
    threshold, which would disable the similarity layer with nothing
    reporting it — a silent failure rather than a loud one."""
    result = cosine_similarity((0.0, 0.0), (1.0, 1.0))
    assert not math.isnan(result)
    assert result == 0.0


def test_cosine_refuses_a_dimension_mismatch() -> None:
    """Comparing a 384-vector against a 512-vector would otherwise return a
    number. After a model swap that number would be meaningless and merges
    would be made on it."""
    with pytest.raises(ValueError, match="dimension mismatch"):
        cosine_similarity((1.0, 0.0), (1.0, 0.0, 0.0))


def test_stub_is_deterministic_and_correctly_shaped() -> None:
    stub = StubEmbedder()
    assert stub.embed(["hello"]) == stub.embed(["hello"])
    assert len(stub.embed(["hello"])[0]) == EMBEDDING_DIMENSION


def test_stub_gives_similar_text_a_higher_score_than_unrelated_text() -> None:
    """The stub has to be directionally right, or every test using it is a lie
    about what the real model would have decided."""
    stub = StubEmbedder()
    a, b, c = stub.embed(
        [
            "backend engineer python payments platform",
            "backend engineer python payments systems",
            "director of facilities and workplace operations",
        ]
    )
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_stub_handles_empty_input_without_dividing_by_zero() -> None:
    vectors = StubEmbedder().embed(["", "  "])
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSION
        assert not any(math.isnan(value) for value in vector)


@pytest.mark.skipif(
    not real_model_available(),
    reason="embedding model not downloaded — run `make model`",
)
class TestTheRealModel:
    """The three claims A5 actually makes. Skipped only when the weights are
    absent, and CI caches them so this never silently stops running there."""

    def test_dimension_matches_what_the_schema_declares(self) -> None:
        """``job_embeddings.embedding`` is ``Vector(384)``. A model returning a
        different width fails at insert time, in production, at 3am."""
        from nightshift.domain.embeddings import FastEmbedEmbedder

        vectors = FastEmbedEmbedder().embed(["a job description"])
        assert len(vectors[0]) == EMBEDDING_DIMENSION

    def test_is_deterministic(self) -> None:
        """A5's central claim, and the reason a hosted API was rejected: the
        dedupe fixture suite cannot be reproducible without this."""
        from nightshift.domain.embeddings import FastEmbedEmbedder

        embedder = FastEmbedEmbedder()
        text = "Senior backend engineer, Python and Go, New York."
        assert embedder.embed([text]) == embedder.embed([text])

    def test_separates_related_from_unrelated_job_text(self) -> None:
        """The property the similarity layer depends on. If this fails the
        threshold is meaningless, whatever number it holds."""
        from nightshift.domain.embeddings import FastEmbedEmbedder

        related_a, related_b, unrelated = FastEmbedEmbedder().embed(
            [
                "Backend engineer building payment services in Python and Go.",
                "Backend engineer for our payments platform, working in Go and Python.",
                "Facilities manager responsible for our office space and vendor contracts.",
            ]
        )
        assert cosine_similarity(related_a, related_b) > cosine_similarity(related_a, unrelated)

    def test_model_name_is_the_one_a5_specifies(self) -> None:
        assert EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"
