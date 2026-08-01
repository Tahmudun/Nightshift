"""The dedupe evaluation suite (PRODUCT-SPEC §7.5, ADR 0010).

Fixture-driven, and ``tests/fixtures/dedupe_pairs.yaml`` is the specification.

The `distinct` cases matter more than the `merge` ones even though they look
like the boring half. A missed merge shows someone the same job twice, which is
obvious and self-correcting the moment they click. A wrong merge removes a real
opening from their view, and they never learn it existed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nightshift.db.base import EmploymentType
from nightshift.domain.dedupe import DedupeCandidate, compare, location_key, normalize_url
from nightshift.domain.embeddings import (
    Embedder,
    StubEmbedder,
    default_embedder,
    real_model_available,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dedupe_pairs.yaml"


def _cases() -> list[dict[str, Any]]:
    return list(yaml.safe_load(FIXTURE.read_text())["cases"])


def _embedder() -> Embedder:
    """The real model when present, the stub otherwise.

    Verdict assertions are only *made* under the real model — see the skip in
    ``test_labelled_pair_gets_the_expected_verdict``. The threshold was derived
    against that model, and a green run against a trigram hash would be
    evidence of nothing. The stub is here so the structural tests (symmetry,
    cross-company blocking) still exercise the similarity code path when the
    weights are absent.
    """
    return default_embedder() if real_model_available() else StubEmbedder()


def _candidate(spec: dict[str, Any], *, company: str = "acme") -> DedupeCandidate:
    description = spec.get("description")
    embedding = _embedder().embed([description])[0] if description else None
    return DedupeCandidate(
        company_key=company,
        canonical_url=spec.get("canonical_url"),
        normalized_title=spec["normalized_title"],
        employment_type=EmploymentType(spec["employment_type"]),
        location_keys=frozenset(spec.get("locations", [])),
        description_hash=spec["description_hash"],
        description=description,
        embedding=embedding,
    )


def _needs_the_real_model(case: dict[str, Any]) -> bool:
    return bool(case["a"].get("description") and case["b"].get("description"))


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_labelled_pair_gets_the_expected_verdict(case: dict[str, Any]) -> None:
    if _needs_the_real_model(case) and not real_model_available():
        pytest.skip("embedding model not downloaded — run `make model`")
    verdict = compare(_candidate(case["a"]), _candidate(case["b"]))
    expected_merge = case["verdict"] == "merge"
    assert verdict.merge is expected_merge, (
        f"{case['name']} ({case['category']}): expected {case['verdict']}, "
        f"got merge={verdict.merge} reason={verdict.reason!r}"
    )
    if expected_merge and "expect_reason" in case:
        assert verdict.reason == case["expect_reason"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_comparison_is_symmetric(case: dict[str, Any]) -> None:
    """``compare(a, b)`` and ``compare(b, a)`` must agree.

    An asymmetric matcher makes merges depend on which posting was ingested
    first, so the same board polled twice would produce different canonical
    jobs — and M1's "byte-identical output twice" criterion would be false at
    the pipeline level while remaining true per-adapter.
    """
    a, b = _candidate(case["a"]), _candidate(case["b"])
    assert compare(a, b).merge == compare(b, a).merge


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_nothing_merges_across_companies(case: dict[str, Any]) -> None:
    """The blocking rule, asserted on every pair in the file.

    Candidate generation already blocks by company, so this is structurally
    unreachable today. It is asserted anyway because a future change to
    candidate generation must not be able to quietly enable it — including for
    the same-URL layer, which otherwise bypasses the other blocking rules.
    """
    a = _candidate(case["a"], company="acme")
    b = _candidate(case["b"], company="globex")
    assert compare(a, b).merge is False


def test_all_seven_categories_are_represented() -> None:
    """A suite missing a category passes while proving nothing about it."""
    categories = {case["category"] for case in _cases()}
    assert categories == {
        "true_duplicate",
        "near_duplicate",
        "distinct_similar_title",
        "repost",
        "seasonal_internship",
        "multi_location",
        "modified_description",
    }


def test_the_suite_contains_both_verdicts_in_useful_numbers() -> None:
    """A file of nothing but `merge` cases is satisfied by `return True`."""
    verdicts = [case["verdict"] for case in _cases()]
    assert verdicts.count("merge") >= 4
    assert verdicts.count("distinct") >= 4


def test_every_merge_verdict_carries_a_reason_and_a_confidence() -> None:
    """I4's spirit: the reason becomes ``job_source_links.link_reason``, and a
    merge nobody can explain is a merge nobody can review."""
    for case in _cases():
        verdict = compare(_candidate(case["a"]), _candidate(case["b"]))
        if verdict.merge:
            assert verdict.reason
            assert 0.0 < verdict.confidence <= 1.0


class TestSimilarityIsConfined:
    """ADR 0010's central constraint, asserted rather than trusted.

    If any of these fail, the layer ordering has been inverted and a number is
    deciding on its own — which is the one thing the human's choice to include
    similarity was made conditional on.
    """

    @staticmethod
    def _pair(**overrides: Any) -> tuple[DedupeCandidate, DedupeCandidate]:
        text = "Backend engineer building payment systems in Python and Go."
        embedding = _embedder().embed([text])[0]
        base: dict[str, Any] = {
            "company_key": "acme",
            "employment_type": EmploymentType.FULL_TIME,
            "location_keys": frozenset({"new york|new york|"}),
            "normalized_title": "backend engineer",
            "description": text,
            "embedding": embedding,
        }
        a = DedupeCandidate(
            **{**base, "canonical_url": "https://boards.greenhouse.io/acme/jobs/90"},
            description_hash="x",
        )
        b = DedupeCandidate(
            **{**base, **overrides, "canonical_url": "https://boards.greenhouse.io/acme/jobs/91"},
            description_hash="y",
        )
        return a, b

    def test_identical_text_still_merges_when_everything_agrees(self) -> None:
        """The control. Without this, the three tests below could pass because
        the similarity layer is broken rather than because it is confined."""
        a, b = self._pair()
        verdict = compare(a, b)
        assert verdict.merge is True
        assert verdict.reason == "similar_description"

    def test_similarity_cannot_overcome_a_different_title(self) -> None:
        a, b = self._pair(normalized_title="staff backend engineer")
        verdict = compare(a, b)
        assert verdict.merge is False
        assert verdict.reason == "different_title"

    def test_similarity_cannot_overcome_a_different_location(self) -> None:
        a, b = self._pair(location_keys=frozenset({"denver|colorado|"}))
        verdict = compare(a, b)
        assert verdict.merge is False
        assert verdict.reason == "no_shared_location"

    def test_similarity_cannot_overcome_a_different_employment_type(self) -> None:
        a, b = self._pair(employment_type=EmploymentType.INTERNSHIP)
        verdict = compare(a, b)
        assert verdict.merge is False
        assert verdict.reason == "different_employment_type"

    def test_similarity_never_outranks_byte_identical_content(self) -> None:
        """Layer 2 compares actual bytes and earns 0.99; layer 3 compares a
        number and is capped below it. A merge's confidence has to reflect what
        was actually checked."""
        from nightshift.domain.dedupe import SIMILARITY_THRESHOLD

        a, b = self._pair()
        assert compare(a, b).confidence <= 0.95
        assert SIMILARITY_THRESHOLD < 1.0


class TestUrlNormalisation:
    def test_tracking_parameters_are_stripped(self) -> None:
        assert normalize_url(
            "https://boards.greenhouse.io/acme/jobs/1?utm_source=x&gh_src=y"
        ) == normalize_url("https://boards.greenhouse.io/acme/jobs/1")

    def test_an_identifying_parameter_is_kept(self) -> None:
        """Some boards put the posting id in the query string. Stripping the
        whole query would collapse such a board into a single job."""
        a = normalize_url("https://example.com/careers?jobId=1")
        b = normalize_url("https://example.com/careers?jobId=2")
        assert a != b

    def test_host_case_and_trailing_slash_do_not_matter(self) -> None:
        assert normalize_url("https://Boards.Greenhouse.IO/acme/jobs/1/") == normalize_url(
            "https://boards.greenhouse.io/acme/jobs/1"
        )

    def test_the_path_is_never_stripped(self) -> None:
        assert normalize_url("https://example.com/a/b") != normalize_url("https://example.com/a/c")

    def test_empty_and_malformed_urls_are_none(self) -> None:
        """None never equals None in the layer-1 check, so an absent URL cannot
        merge two jobs by matching another absent URL."""
        for value in (None, "", "   ", "not-a-url"):
            assert normalize_url(value) is None

    def test_two_jobs_without_urls_do_not_match_on_layer_one(self) -> None:
        a = DedupeCandidate(
            company_key="acme",
            canonical_url=None,
            normalized_title="a",
            employment_type=EmploymentType.FULL_TIME,
            location_keys=frozenset({"new york|new york|"}),
            description_hash="x",
        )
        b = DedupeCandidate(
            company_key="acme",
            canonical_url=None,
            normalized_title="b",
            employment_type=EmploymentType.FULL_TIME,
            location_keys=frozenset({"new york|new york|"}),
            description_hash="y",
        )
        assert compare(a, b).merge is False


class TestLocationKey:
    def test_is_case_insensitive(self) -> None:
        assert location_key("New York", "New York", None) == location_key(
            "new york", "NEW YORK", None
        )

    def test_distinguishes_cities(self) -> None:
        assert location_key("New York", "New York", None) != location_key(
            "Denver", "Colorado", None
        )

    def test_nulls_are_empty_rather_than_the_string_none(self) -> None:
        """`str(None)` would make an unparsed location match another unparsed
        one, merging two jobs on the basis of two failures."""
        assert location_key(None, None, None) == "||"
