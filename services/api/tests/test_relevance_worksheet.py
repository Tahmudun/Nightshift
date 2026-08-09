"""The relevance worksheet generator, and the committed ratings file.

M3a's worksheet asked a human for facts with right answers. This one asks for a
judgement that has none (`matching.md` §7.3), which changes what can be tested:
nothing here can check whether a rating is *correct*. What it can check is that
the thirty postings put in front of a person are worth their twenty minutes, and
that whatever they write back is readable by M3d without guessing.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
RATINGS = ROOT / "services" / "api" / "tests" / "fixtures" / "relevance" / "ratings.yaml"


@pytest.fixture(scope="module")
def worksheet() -> Any:
    spec = importlib.util.spec_from_file_location(
        "make_relevance_worksheet", ROOT / "scripts" / "make_relevance_worksheet.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_relevance_worksheet"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def corpus(worksheet: Any) -> list[tuple[str, dict[str, Any]]]:
    return list(worksheet._label_worksheet().all_postings())


@pytest.fixture(scope="module")
def ratings() -> dict[str, Any]:
    return yaml.safe_load(RATINGS.read_text(encoding="utf-8"))


# -- the selection -------------------------------------------------------


def test_the_same_corpus_yields_the_same_thirty(
    worksheet: Any, corpus: list[tuple[str, dict[str, Any]]]
) -> None:
    """Regenerating must never reshuffle work a human has already done."""
    first = [(b, p["id"]) for b, p in worksheet.select_for_rating(corpus)]
    second = [(b, p["id"]) for b, p in worksheet.select_for_rating(list(reversed(corpus)))]
    assert first == second
    assert len(first) == worksheet.WORKSHEET_TARGET


def test_the_set_spreads_across_employers_and_role_shapes(
    worksheet: Any, corpus: list[tuple[str, dict[str, Any]]]
) -> None:
    """The anti-vacuity check, one milestone down from M3b's.

    A worksheet of thirty accountants produces thirty `poor` ratings, and a
    ranker that sorts accountants last would then score perfectly while being
    useless. The measurement needs roles this person might plausibly want *and*
    roles they would not, or it measures nothing.
    """
    selected = worksheet.select_for_rating(corpus)
    buckets = Counter(worksheet.bucket_of(p["title"]) for _, p in selected)
    boards = {b for b, _ in selected}

    assert len(boards) >= 5, boards
    assert buckets["technical_early"] >= 8, buckets
    assert buckets["technical_experienced"] >= 5, buckets
    assert buckets["non_technical"] >= 3, buckets


def test_a_posting_that_is_not_a_role_is_never_selected(
    worksheet: Any, corpus: list[tuple[str, dict[str, Any]]]
) -> None:
    """Akuna's "Talent Community" and Old Mission's "General Submission" are in
    the corpus and are not jobs. A good/poor rating on one is a coin flip
    recorded as a judgement."""
    titles = [p["title"] for _, p in worksheet.select_for_rating(corpus)]
    assert titles, "the corpus produced nothing to check"
    for title in titles:
        assert not worksheet._NOT_A_JOB.search(title), title


def test_the_same_job_in_different_clothes_is_rated_once(worksheet: Any) -> None:
    """Point72 posts one Academy internship for three cities; Jump posts the
    same campus role full-time and as an internship. Three slots of thirty."""
    stem = worksheet.title_stem
    assert stem("2027 Academy Program - Hong Kong") == stem("2027 Academy Program - Japan")
    assert stem("Software Engineer Intern, Summer 2027") == stem("Software Engineer Intern")
    assert stem("Hardware Engineer") != stem("Software Engineer")


def test_a_recruiting_role_is_not_an_early_career_role(worksheet: Any) -> None:
    """A recruiting job carries the early-career vocabulary.

    "University Recruiter" and "Campus Recruiter" contain the early-career
    vocabulary and are jobs recruiting students, not jobs for them — the same
    mistake M3a's `_MISLEADING_FOR_ITS_REASON` was measured into fixing."""
    assert worksheet.bucket_of("University Recruiter") == "non_technical"
    assert worksheet.bucket_of("Campus Recruiter, Early Careers") == "non_technical"
    assert worksheet.bucket_of("Software Engineer Intern") == "technical_early"
    assert worksheet.bucket_of("Staff Software Engineer") == "technical_experienced"


def test_a_posting_whose_requirements_cannot_be_shown_goes_last(
    worksheet: Any, corpus: list[tuple[str, dict[str, Any]]]
) -> None:
    """Shown able to fail: without the `has_requirements` sort, the first pick in
    a cell is whatever sorted first by title, marked-guess excerpt and all."""
    label = worksheet._label_worksheet()
    with_sort = worksheet.select_for_rating(corpus, has_requirements=label.has_requirements_heading)
    without = worksheet.select_for_rating(corpus)

    def showable(selected: list[tuple[str, dict[str, Any]]]) -> int:
        return sum(1 for _, p in selected if label.has_requirements_heading(p["text"]))

    assert showable(with_sort) >= showable(without)
    assert showable(with_sort) >= len(with_sort) - 3


# -- the committed file --------------------------------------------------


def test_the_ratings_file_is_readable_without_guessing(ratings: dict[str, Any]) -> None:
    assert set(ratings) == {"rated_on", "profile", "ratings"}
    entries = ratings["ratings"]
    assert len(entries) == 30
    assert [e["n"] for e in entries] == list(range(1, 31))
    assert len({(e["board"], e["id"]) for e in entries}) == 30


def test_every_rating_is_one_of_the_three_buckets_or_still_blank(
    worksheet: Any, ratings: dict[str, Any]
) -> None:
    """Passes trivially while the file is blank and fails on the first typo.

    That is the intended shape rather than a weak test: the file is filled in by
    hand, in one sitting, and a capitalised `Good` or a stray `great` would
    otherwise surface as a silently dropped row in M3d's metric — where it would
    look like a ranking result rather than a spelling.
    """
    allowed = {worksheet.TO_RATE, *worksheet.RATING_VALUES}
    for entry in ratings["ratings"]:
        assert entry["rating"] in allowed, f"[{entry['n']}] {entry['title']}: {entry['rating']!r}"


def test_a_filled_profile_uses_skill_names_the_matcher_can_resolve(
    worksheet: Any, ratings: dict[str, Any]
) -> None:
    """Checked only once written, and worth checking then.

    A profile listing "javascript" or "React.js" is a profile whose skills the
    vocabulary silently does not match, and the ranking would then be graded on
    a person the scorer cannot see. `data/skills.yaml` is case-sensitive on
    purpose for the names that are also English words.
    """
    from nightshift.domain.skill_vocabulary import load_vocabulary

    skills = ratings["profile"]["skills"]
    if skills == worksheet.TO_RATE:
        pytest.skip("profile not filled in yet — QUESTIONS Q5")

    vocabulary = load_vocabulary()
    unresolved = [name for name in skills if vocabulary.canonical(name) == name]
    known = set(vocabulary.canonical_names)
    assert not [name for name in unresolved if name not in known], unresolved
