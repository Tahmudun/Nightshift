"""Eligibility precision and recall, per state. `matching.md` §7.1, row one.

M3d Task 3, and the row of §7.1's table that had nothing behind it at all — M3b
published reading accuracy and classifier accuracy and said so; no test anywhere
has ever compared a *verdict* to anything.

## What this measures, and the half it cannot

There is no labeled verdict in this repository and there deliberately never will
be. §3.1: a verdict bakes the labeler's own graduation date and authorization
status into a fixture, both of those change, and when they do every label
silently becomes wrong while continuing to pass. What is labeled is what each
posting *requires*; the verdict is computed.

So two different quantities exist here and only one of them is free:

* **Extraction-induced verdict error**, measured below. Ground truth is
  ``evaluate(reading built from the label, profile)``; the prediction is
  ``evaluate(reading built from the extractor, profile)``. The rules are
  identical on both sides, so what this isolates is **how often mis-reading a
  posting changes the verdict** — which is exactly the path by which a wrong
  `ineligible` reaches a person, and A13 makes that the worst output this engine
  can produce.
* **Rule correctness** — whether ``evaluate(label, profile)`` is itself the right
  answer. Nothing here measures that. It needs a human reading 60 postings and
  writing a verdict per profile, which §3.1 refuses for the reason above.

Reporting the first as "eligibility precision and recall" without this paragraph
would be the flattering reading of a real number. PROGRESS carries the same
sentence under "Not real yet".

## Reported, not gated

M3a's rule: a floor picked before measuring is either unreachable or vacuous and
there is no way to tell which from outside. These numbers have never been seen
before, so this file prints them and asserts only the things that are true by
construction — the confusion matrix adds up, the corpus reaches more than one
state, the grader can fail, and **no posting is turned `ineligible` by extraction
error alone**. That last one is not a floor set by taste; it is A13.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from nightshift.db.base import WorkAuthorization
from nightshift.domain.eligibility import SeekerProfile, evaluate
from nightshift.domain.eligibility_labels import PostingLabel, load_answer_key
from nightshift.domain.eligibility_reading import PostingReading, read_posting
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.test_requirement_extraction_against_the_answer_key import _corpus_postings

PROFILES_FILE = Path(__file__).parent / "fixtures" / "eligibility" / "profiles.yaml"

#: Every state a rule can reach. `likely_eligible` is deliberately absent from
#: the gate (ADR 0017) and would make every metric below undefined for it.
STATES: tuple[str, ...] = (
    "eligible",
    "uncertain",
    "likely_ineligible",
    "ineligible",
)


@dataclass
class Confusion:
    """One (truth, predicted) tally, and the two rates §3.3 insists are separate.

    Precision and recall are reported per state and never averaged into one
    number, because a gate answering `uncertain` to everything has perfect
    precision on every other state and is worthless. One figure would hide that
    exactly as well as it hides the opposite failure.
    """

    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def record(self, truth: str, predicted: str) -> None:
        self.counts[(truth, predicted)] += 1

    def true_positives(self, state: str) -> int:
        return self.counts[(state, state)]

    def predicted(self, state: str) -> int:
        return sum(n for (_, p), n in self.counts.items() if p == state)

    def actual(self, state: str) -> int:
        return sum(n for (t, _), n in self.counts.items() if t == state)

    def precision(self, state: str) -> float | None:
        """`None` when the state was never predicted — never 1.0.

        A state nobody predicted has no precision, and returning a number there
        would put a perfect score beside a row that was never exercised. That is
        the same rule `score_fraction` follows one subsystem over, for the same
        reason: zero and undefined are different claims.
        """
        denominator = self.predicted(state)
        return self.true_positives(state) / denominator if denominator else None

    def recall(self, state: str) -> float | None:
        denominator = self.actual(state)
        return self.true_positives(state) / denominator if denominator else None

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def agreements(self) -> int:
        return sum(n for (t, p), n in self.counts.items() if t == p)


def reading_from_label(label: PostingLabel) -> PostingReading:
    """The answer key as the gate would have read it, had it read perfectly.

    `PostingReading`'s own docstring says it is field-for-field comparable with
    `PostingLabel` minus the technology lists, and this is that correspondence
    written down and executed rather than described.

    **`evidence` is empty and that is not a shortcut.** A blocker quotes the
    proposal it came from, and a label has no character offsets — it is a human's
    reading, not a span. The gate's *state* never depends on evidence, only its
    quoted explanation does, so the truth side is unaffected;
    `test_the_truth_reading_carries_no_invented_evidence` pins that the emptiness
    is deliberate rather than a field somebody forgot.
    """
    return PostingReading(
        degree=label.degree,
        graduation_window=label.graduation_window,
        min_years_experience=label.min_years_experience,
        enrollment_required=label.enrollment_required,
        sponsorship=label.sponsorship,
    )


def load_profiles() -> tuple[tuple[str, SeekerProfile], ...]:
    raw = yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8"))
    profiles = []
    for entry in raw["profiles"]:
        fields = {k: v for k, v in entry.items() if k != "name"}
        authorization = fields.pop("work_authorization", None)
        profiles.append(
            (
                entry["name"],
                SeekerProfile(
                    **fields,
                    work_authorization=(
                        WorkAuthorization(authorization)
                        if authorization
                        else WorkAuthorization.UNSPECIFIED
                    ),
                ),
            )
        )
    return tuple(profiles)


@pytest.fixture(scope="module")
def graded() -> dict[str, Any]:
    """Every (posting, profile) pair, scored both ways."""
    key = load_answer_key()
    vocabulary = load_vocabulary()
    profiles = load_profiles()
    postings = _corpus_postings()

    overall = Confusion()
    per_profile: dict[str, Confusion] = {name: Confusion() for name, _ in profiles}
    false_blocks: list[str] = []

    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings[board][posting_id]
            truth_reading = reading_from_label(label)
            predicted_reading = read_posting(extract_requirements(text, vocabulary=vocabulary))
            for name, profile in profiles:
                truth = evaluate(truth_reading, profile).state.value
                predicted = evaluate(predicted_reading, profile).state.value
                overall.record(truth, predicted)
                per_profile[name].record(truth, predicted)
                if predicted == "ineligible" and truth != "ineligible":
                    false_blocks.append(f"{board}/{posting_id} · {name}: {truth} -> ineligible")

    return {
        "overall": overall,
        "per_profile": per_profile,
        "false_blocks": false_blocks,
        "profiles": profiles,
        "postings": sum(len(b) for b in key.boards.values()),
    }


def test_report_the_numbers(graded: dict[str, Any], capsys: Any) -> None:
    """Always passes. Prints what the gate actually does. Run with `-s`."""
    overall: Confusion = graded["overall"]
    with capsys.disabled():
        print(
            f"\n  eligibility verdicts: {graded['postings']} postings x "
            f"{len(graded['profiles'])} profiles = {overall.total} pairs"
        )
        print(f"  agreement with the labeled reading: {overall.agreements}/{overall.total}\n")
        print(f"  {'state':<20}{'truth':>7}{'pred':>7}{'prec':>9}{'recall':>9}")
        for state in STATES:
            precision = overall.precision(state)
            recall = overall.recall(state)
            print(
                f"  {state:<20}{overall.actual(state):>7}{overall.predicted(state):>7}"
                f"{'  —' if precision is None else f'{precision:>9.3f}'}"
                f"{'  —' if recall is None else f'{recall:>9.3f}'}"
            )
        print()
        for name, confusion in graded["per_profile"].items():
            print(f"  {name:<32} agreement {confusion.agreements}/{confusion.total}")
        print()
        disagreements = sorted(
            ((n, t, p) for (t, p), n in overall.counts.items() if t != p), reverse=True
        )
        for count, truth, predicted in disagreements[:6]:
            print(f"    read {predicted!r} where the label says {truth!r}  x{count}")
        print()


def test_no_posting_is_blocked_by_extraction_error_alone(graded: dict[str, Any]) -> None:
    """A13, and the one assertion here that is not waiting for a baseline.

    Every other error in this system is visible: a wrong score sits beside its
    breakdown, a missing skill sits in the gap list. A wrong `ineligible` removes
    an opportunity from somebody's world and reports nothing — they never learn
    it existed. So a *reading* mistake that turns a posting the labels say is
    open into one the gate refuses is the failure worth a hard zero rather than a
    floor set just under whatever today happens to produce.

    The converse is not asserted, deliberately: extraction error that turns an
    `ineligible` into an `uncertain` shows the person a posting they cannot have,
    which costs them a click and costs them nothing they cannot see.
    """
    assert graded["false_blocks"] == [], (
        "extraction error produced a hard block the answer key does not support:\n  "
        + "\n  ".join(graded["false_blocks"])
    )


def test_the_confusion_matrix_accounts_for_every_pair(graded: dict[str, Any]) -> None:
    """Arithmetic, and the guard against a state nobody enumerated.

    `STATES` is hand-written. If the gate ever reaches a state missing from it,
    the per-state rows silently stop summing to the total rather than failing —
    the same hand-maintained-list defect this project has now found three times.
    """
    overall: Confusion = graded["overall"]
    assert overall.total == graded["postings"] * len(graded["profiles"])
    assert sum(overall.actual(state) for state in STATES) == overall.total
    assert sum(overall.predicted(state) for state in STATES) == overall.total


def test_the_truth_set_reaches_more_than_one_state(graded: dict[str, Any]) -> None:
    """The anti-vacuity guard, and the one M3b's gate taught this project to write.

    A gate answering `uncertain` to all 240 pairs scores perfect precision on
    every other state, and a corpus where the truth is one constant makes every
    metric above meaningless while all of them read as successes.
    """
    overall: Confusion = graded["overall"]
    reached = {state for state in STATES if overall.actual(state)}
    assert len(reached) >= 3, f"the labeled corpus only ever reaches {sorted(reached)}"
    assert overall.actual("ineligible"), (
        "no pair is `ineligible` under the labels, so that row's precision and "
        "recall are undefined and the state is untested"
    )


def test_the_grader_can_fail(graded: dict[str, Any]) -> None:
    """A confusion matrix that cannot record a disagreement reads as 1.000.

    Asserted against a difference constructed here rather than found in the
    corpus, exactly as `test_the_grader_can_fail` does one file over — this
    project has now shipped three tests whose comparison could not see the thing
    they existed to find.
    """
    confusion = Confusion()
    confusion.record("eligible", "eligible")
    confusion.record("eligible", "ineligible")

    assert confusion.precision("eligible") == 1.0
    assert confusion.recall("eligible") == 0.5
    assert confusion.precision("ineligible") == 0.0
    # Never predicted, so it has no precision — not a perfect one.
    assert confusion.precision("uncertain") is None
    assert confusion.recall("ineligible") is None


def test_the_truth_reading_carries_no_invented_evidence() -> None:
    """A label has no character offsets, so the truth reading quotes nothing.

    The temptation is to fill `evidence` with something plausible so blockers
    read nicely in a failure message. That would be a fabricated span on the side
    of the comparison that defines correctness, which is §7.2 pointed at itself.
    """
    label = next(iter(next(iter(load_answer_key().boards.values())).values()))

    assert reading_from_label(label).evidence == ()


def test_every_profile_in_the_fixture_is_distinct_and_loaded() -> None:
    """Four profiles, and `states_nothing` really is empty.

    A YAML entry with only a name parses to an all-null profile, which is the
    intent — but it also parses that way if somebody deletes its fields by
    accident, so the emptiness is asserted rather than assumed.
    """
    profiles = load_profiles()
    names = [name for name, _ in profiles]

    assert len(names) == len(set(names)) == 4
    empty = dict(profiles)["states_nothing"]
    assert empty == SeekerProfile()


def test_a_false_block_would_be_caught(graded: dict[str, Any]) -> None:
    """`test_no_posting_is_blocked_by_extraction_error_alone` passed on its first
    run, and a hard-zero assertion that has never been red is indistinguishable
    from one that cannot go red.

    So the detection is exercised against a constructed disagreement rather than
    trusted: a posting the labels say offers sponsorship, mis-read as refusing
    it, against the one profile that needs it. That is the exact shape of the
    error A13 calls the worst this engine can produce — and it is the shape the
    corpus happens not to contain, which is a fact about the corpus and not
    evidence about the detector.
    """
    profile = dict(load_profiles())["no_degree_needs_sponsorship"]
    truthful = PostingReading(
        degree="none",
        graduation_window="not_stated",
        min_years_experience=None,
        enrollment_required="not_stated",
        sponsorship="offered",
    )
    misread = PostingReading(**{**truthful.__dict__, "sponsorship": "not_offered"})

    truth = evaluate(truthful, profile).state.value
    predicted = evaluate(misread, profile).state.value

    assert truth != "ineligible"
    assert predicted == "ineligible"
    # The condition the fixture applies, on a pair that meets it.
    assert predicted == "ineligible" and truth != "ineligible"
