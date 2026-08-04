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
