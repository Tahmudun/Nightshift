"""The eligibility selectors, exercised against the committed Datadog payload.

A selector that matches nothing is a selector that will silently contribute no
postings to the corpus, and the corpus is the answer key. These tests are how
that stays visible.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_recorder() -> Any:
    """Import scripts/record_fixture.py, which is not a package module."""
    spec = importlib.util.spec_from_file_location(
        "record_fixture", ROOT / "scripts" / "record_fixture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["record_fixture"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recorder() -> Any:
    return _load_recorder()


def test_content_text_strips_html_and_unescapes_entities(recorder: Any) -> None:
    job = {"content": "&lt;p&gt;Bachelor&#39;s degree&lt;/p&gt;"}
    assert recorder._content_text(job) == "Bachelor's degree"


def test_content_text_collapses_whitespace(recorder: Any) -> None:
    job = {"content": "&lt;li&gt;3+   years\n\n  of experience&lt;/li&gt;"}
    assert recorder._content_text(job) == "3+ years of experience"


def test_every_eligibility_selector_has_a_reason_and_a_limit(recorder: Any) -> None:
    for why, predicate, limit in recorder.ELIGIBILITY_SELECTORS:
        assert why and isinstance(why, str)
        assert callable(predicate)
        assert limit >= 1


def test_the_phd_selector_matches_the_datadog_research_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """The posting that motivated the `+equivalent` label field.

    Its text reads "You hold a PhD in Computer Science... (or have equivalent
    experience)", which is `matching.md` §3.2's worked example.
    """
    jobs = greenhouse_board_payload["jobs"]
    matched = [j for j in jobs if recorder._mentions_doctorate(j)]
    assert [j["title"] for j in matched] == ["AI Research Scientist - Datadog AI Research (DAIR)"]


def test_the_equivalence_selector_matches_the_same_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    jobs = greenhouse_board_payload["jobs"]
    matched = [j["title"] for j in jobs if recorder._mentions_equivalence(j)]
    assert "AI Research Scientist - Datadog AI Research (DAIR)" in matched


def test_curate_never_returns_the_same_posting_twice(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Two selectors can match one posting; the fixture must not duplicate it."""
    jobs = greenhouse_board_payload["jobs"]
    picked, reasons = recorder.curate(jobs, recorder.ELIGIBILITY_SELECTORS)
    ids = [j["id"] for j in picked]
    assert len(ids) == len(set(ids))
    assert set(reasons) == {str(i) for i in ids}


def test_the_sponsorship_selector_does_not_match_executive_sponsor(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Regression guard for Finding 1: real fixture text, job 7762722.

    "Serve as an executive sponsor for strategic customers across North
    America" is a sales usage of "sponsor", not an immigration one.
    """
    jobs = greenhouse_board_payload["jobs"]
    sales_vp = next(j for j in jobs if j["id"] == 7762722)
    assert "executive sponsor" in recorder._content_text(sales_vp).lower()
    assert recorder._mentions_sponsorship(sales_vp) is False


def test_the_sponsorship_selector_matches_visa_sponsorship(recorder: Any) -> None:
    """Invented text: the fixture has no real immigration-sponsorship posting."""
    job = {"content": "We are able to provide visa sponsorship for this role."}
    assert recorder._mentions_sponsorship(job) is True


def test_the_sponsorship_selector_matches_work_authorization_us_and_uk_spelling(
    recorder: Any,
) -> None:
    """Invented text, covering both spellings the fixed regex claims to catch."""
    us = {"content": "We cannot sponsor work authorization for this position."}
    uk = {"content": "We cannot sponsor work authorisation for this position."}
    assert recorder._mentions_sponsorship(us) is True
    assert recorder._mentions_sponsorship(uk) is True


def test_states_graduation_year_matches_a_stated_year(recorder: Any) -> None:
    """Invented text: no posting on the committed board states a graduation year."""
    job = {"content": "Open to candidates graduating in 2027 or later."}
    assert recorder._states_graduation_year(job) is True


def test_states_years_of_experience_matches_the_real_sales_engineering_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Real fixture text, job 7762722: "...10+ years of experience...".'"""
    jobs = greenhouse_board_payload["jobs"]
    sales_vp = next(j for j in jobs if j["id"] == 7762722)
    assert recorder._states_years_of_experience(sales_vp) is True


def test_has_preferred_section_matches_the_real_research_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Real fixture text, job 6572669: contains a "Bonus Points" section."""
    jobs = greenhouse_board_payload["jobs"]
    researcher = next(j for j in jobs if j["id"] == 6572669)
    assert "bonus points" in recorder._content_text(researcher).lower()
    assert recorder._has_preferred_section(researcher) is True


def test_curate_with_one_argument_matches_curate_with_greenhouse_selectors_explicit(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Locks the backward-compatibility requirement: existing callers of
    `curate(jobs)` must keep getting the location-shape selectors."""
    jobs = greenhouse_board_payload["jobs"]
    assert recorder.curate(jobs) == recorder.curate(jobs, recorder.GREENHOUSE_SELECTORS)


def test_unmatched_shapes_does_not_report_a_gap_the_board_does_not_have(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Regression guard for Finding 2, on the real fixture.

    Job 6572669 matches both `_mentions_doctorate` and `_mentions_equivalence`.
    `curate` is greedy and doctorate is listed first, so it claims the posting
    and the equivalence selector contributes nothing to `reasons` — but the
    board plainly contains the equivalence phrase, so it must not be reported
    as a gap.
    """
    jobs = greenhouse_board_payload["jobs"]
    gaps = recorder.unmatched_shapes(jobs, recorder.ELIGIBILITY_SELECTORS)
    assert "'or equivalent experience' — the A13 escape hatch" not in gaps
