"""The extractor, graded against sixty postings a human labeled by hand.

`docs/architecture/matching.md` §1.1: the answer key was committed before these
rules were written, so this measures the rules rather than the choice of
examples.

The floors below are **measured, not chosen**. Run the reporting test, read the
numbers, set each floor just under what the extractor actually achieves, and
raise them as it improves. A floor picked before measuring is either
unreachable or vacuous, and there is no way to tell which from the outside.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.domain.eligibility_labels import load_answer_key
from nightshift.domain.extraction_metrics import Score, score_sets
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.skill_vocabulary import load_vocabulary

CORPUS = Path(__file__).resolve().parent / "fixtures" / "eligibility"

#: Measured on the committed corpus at m3a.1. Update alongside a rule change,
#: and never downward without a sentence in the commit saying what regressed.
#: Measured at m3a.1 on 2026-08-04, then rounded down to two places:
#:
#:     required technology  precision 0.659  recall 0.459   (tp 56 fp 29 fn 66)
#:     necessity accuracy   0.668  over 199 labeled technologies
#:
#: Recall is the weaker figure and it is honest about why: 60 of the 103
#: originally missed technologies are terms `data/skills.yaml` does not carry
#: at all — GCP, JAX, LangChain, HuggingFace, DSPy, SIEM, EDR — so no rule
#: change can find them. That is a vocabulary gap, recorded in PROGRESS, not
#: an extraction gap.
REQUIRED_TECH_PRECISION_FLOOR = 0.65
REQUIRED_TECH_RECALL_FLOOR = 0.45
NECESSITY_ACCURACY_FLOOR = 0.66


def _description(job: dict[str, Any]) -> str:
    import html
    import re

    raw = (
        job.get("content")
        or job.get("descriptionPlain")
        or job.get("descriptionHtml")
        or job.get("description")
        or ""
    )
    text = html.unescape(html.unescape(str(raw)))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _corpus_postings() -> dict[str, dict[str, str]]:
    """board -> posting id -> description text."""
    out: dict[str, dict[str, str]] = {}
    for path in sorted(CORPUS.glob("*.json")):
        if path.name.endswith(".meta.json") or path.name == "labels.yaml":
            continue
        body = json.loads(path.read_text())
        jobs = body["jobs"] if isinstance(body, dict) else body
        out[path.stem] = {str(j.get("id")): _description(j) for j in jobs}
    return out


@pytest.fixture(scope="module")
def graded() -> dict[str, Any]:
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()

    tech_tp = tech_fp = tech_fn = 0
    necessity_right = necessity_total = 0
    misses: list[str] = []

    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings.get(board, {}).get(posting_id)
            assert text is not None, f"{board}/{posting_id} labeled but not in corpus"
            proposals = extract_requirements(text, vocabulary=vocab)

            predicted_required = {
                p.value for p in proposals if p.kind == "technology" and p.necessity == "required"
            }
            s = score_sets(predicted_required, set(label.required_tech))
            tech_tp += s.true_positives
            tech_fp += s.false_positives
            tech_fn += s.false_negatives
            if s.false_negatives:
                misses.append(
                    f"{board}/{posting_id}: missed "
                    f"{sorted(set(label.required_tech) - predicted_required)}"
                )

            # Necessity accuracy: of the technologies the human placed in
            # either list, how many did the extractor put in the right one.
            for tech in label.required_tech:
                necessity_total += 1
                necessity_right += int(
                    tech.casefold() in {t.casefold() for t in predicted_required}
                )
            # The nice-to-have half asks only that the extractor did *not* call
            # it required — deliberately, and not the stricter "found it and
            # called it preferred". A term `skills.yaml` does not carry cannot
            # be called required either, so the strict version would score a
            # vocabulary gap as a necessity failure and move a number that is
            # supposed to be about headings.
            #
            # What it costs is worth stating: this half is satisfied by an
            # extractor that finds nothing at all. It is meaningful only read
            # beside the recall figure above, which is why neither is ever
            # collapsed into one score.
            for tech in label.mentioned_not_required:
                necessity_total += 1
                necessity_right += int(
                    tech.casefold() not in {t.casefold() for t in predicted_required}
                )

    return {
        "tech": Score(tech_tp, tech_fp, tech_fn),
        "necessity_accuracy": (1.0 if necessity_total == 0 else necessity_right / necessity_total),
        "necessity_total": necessity_total,
        "misses": misses,
    }


def test_report_the_numbers(graded: dict[str, Any], capsys: Any) -> None:
    """Always passes. Prints what the extractor actually does, so the floors
    below are set from measurement rather than from hope.

    Run with `-s` to read it.
    """
    tech: Score = graded["tech"]
    with capsys.disabled():
        print(
            f"\n  required technology  precision {tech.precision:.3f}"
            f"  recall {tech.recall:.3f}"
            f"  (tp {tech.true_positives} fp {tech.false_positives} "
            f"fn {tech.false_negatives})"
        )
        print(
            f"  necessity accuracy   {graded['necessity_accuracy']:.3f}"
            f"  over {graded['necessity_total']} labeled technologies"
        )
        for miss in graded["misses"][:15]:
            print(f"    {miss}")


def test_required_technology_precision_holds(graded: dict[str, Any]) -> None:
    """Precision matters more than recall here: a technology wrongly called
    required becomes a false gap in the explanation, which is a visible lie."""
    assert graded["tech"].precision >= REQUIRED_TECH_PRECISION_FLOOR


def test_required_technology_recall_holds(graded: dict[str, Any]) -> None:
    assert graded["tech"].recall >= REQUIRED_TECH_RECALL_FLOOR


def test_necessity_accuracy_holds(graded: dict[str, Any]) -> None:
    assert graded["necessity_accuracy"] >= NECESSITY_ACCURACY_FLOOR


def test_no_nice_to_have_is_ever_reported_as_required(
    graded: dict[str, Any],
) -> None:
    """The one assertion with no floor, because the honest floor is zero.

    A technology the human put under "nice to have" appearing as `required` is
    the failure that produces nine false gaps against a qualified candidate.
    """
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()
    violations: list[str] = []
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings[board][posting_id]
            required = {
                p.value.casefold()
                for p in extract_requirements(text, vocabulary=vocab)
                if p.kind == "technology" and p.necessity == "required"
            }
            for tech in label.mentioned_not_required:
                if tech.casefold() in required:
                    violations.append(f"{board}/{posting_id}: {tech}")
    assert violations == [], violations
