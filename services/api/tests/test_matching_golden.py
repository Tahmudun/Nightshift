"""The golden test: what the scorer produces, written down before it is tuned.

`matching.md` §4.2 asks for a test that pins the full score and evidence output
over the fixture corpus, so that **changing a rule without bumping
`RULESET_LOGIC_VERSION` goes red with a diff showing exactly what moved**. §8
asks for the determinism half: same fixtures, two runs, byte-identical.

## Written before any weight is tuned, and that ordering is the whole point

The M3c plan §1.3 commits to this and it is not a formality. A golden file
written *after* tuning pins whatever the code does at that moment, which makes
it a record of the tuned output rather than a check on it — the same defect
`matching.md` §1.1 names for an evaluation written after the thing it evaluates.
Written first, it turns every subsequent weight change into a visible diff that
somebody has to look at and accept.

The committed weights are therefore §5.1's published numbers, unmeasured and
untuned, and this file records what they produce. Task 7 will move some of them
and the diff is the deliverable.

## Regenerating, and the one path this file exists to block

    NIGHTSHIFT_UPDATE_GOLDEN=1 pytest tests/test_matching_golden.py

The failure mode a golden test invites is the developer who changes a rule, sees
red, regenerates, and commits — leaving `ruleset_version` describing rules that
no longer exist. Every stored `match_results` row then claims to have been
computed under a ruleset that never produced it, and §4.2's "a stale result is
never silently served" quietly stops being true, because staleness is decided by
comparing that version.

So regeneration **refuses** when a score that exists in both the committed file
and the new one changed while the version stayed put. Growing the corpus is
allowed — new blocks change no existing score — because a corpus addition is not
a rule change and treating it as one would teach people to override the guard.

## Why this corpus and not the labeled 60

All 153 recorded postings across the nine boards, not the 60 with answer-key
labels. Nothing here is graded against a key — the golden file makes no claim
about whether a score is *right* — so the labels buy nothing and the extra 93
postings buy coverage: more seniority levels, more cities, more postings with no
publication date at all.

It is still nine employers, all quant trading firms or AI labs (PROGRESS records
this about the whole M3 corpus). A rule that only misfires on a hospital's
posting is not visible here, and this file cannot pretend otherwise.
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from nightshift.db.base import MatchComponent
from nightshift.domain.matching_weights import load_weights, ruleset_version
from nightshift.domain.scoring import MatchScore, ScoringProfile, score_match
from tests.matching_corpus import AS_OF, CorpusPosting, load_corpus, load_profiles

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_FILE = FIXTURES / "matching" / "golden.txt"

UPDATE = os.environ.get("NIGHTSHIFT_UPDATE_GOLDEN") == "1"


class GoldenRefusedError(Exception):
    """Regeneration would rewrite a score without bumping the version."""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_SHORT = {
    MatchComponent.ROLE: "role",
    MatchComponent.SKILL: "skill",
    MatchComponent.PROJECT: "project",
    MatchComponent.LOCATION: "location",
    MatchComponent.FRESHNESS: "freshness",
    MatchComponent.PRIORITY: "priority",
}


#: What an unassessable component prints where its points would go. **Not `0`**,
#: and the whole of §5.1.1 is why: a component that scored zero and a component
#: the posting could not answer are different statements, and a golden file that
#: renders both as `0` cannot show a rule change that turns one into the other.
NOT_ASSESSED = "—"


def _render_score(key: str, profile_name: str, score: MatchScore) -> list[str]:
    """One score as text. Text rather than JSON because the diff is the product.

    A JSON golden file diffs one key per line and buries the number that moved
    among its punctuation; this reads as a breakdown, which is what somebody
    staring at a red test needs.

    Every component prints its `why` whether or not it scored. That sentence is
    what the explanation panel renders (§6), so a rule that changes its wording
    without changing its arithmetic has changed what a person is told — and a
    golden file pinning only the numbers would call that no change at all.
    """
    by_component = {c.component: c for c in score.components}
    summary = " · ".join(
        f"{_SHORT[c]} {by_component[c].points if by_component[c].assessable else NOT_ASSESSED}"
        for c in MatchComponent
    )
    lines = [
        f"{key} · {profile_name}",
        f"  {score.overall}/{score.assessed_out_of}  {summary} · penalty {score.penalty_total}",
    ]
    for component in MatchComponent:
        scored_component = by_component[component]
        points = scored_component.points if scored_component.assessable else NOT_ASSESSED
        lines.append(f"  {_SHORT[component]:<9} {points:>3}  {scored_component.why}")
        for row in scored_component.evidence:
            detail = []
            if row.job_span_text is not None:
                detail.append(
                    f'job "{row.job_span_text}" @{row.job_char_start}-{row.job_char_end}'
                    f" [{row.job_span_field}]"
                )
            if row.user_span_text is not None:
                detail.append(f'user "{row.user_span_text}"')
            if row.compared:
                detail.append(json.dumps(row.compared, sort_keys=True))
            lines.append(f"       {row.points:>3}  " + " · ".join(detail))
    for penalty in score.penalties:
        cost = penalty.points if penalty.applicable else NOT_ASSESSED
        lines.append(f"  penalty {penalty.name} {cost}  {penalty.why}")
    return lines


def render_golden(
    corpus: tuple[CorpusPosting, ...],
    profiles: tuple[tuple[str, ScoringProfile], ...],
    scores: dict[tuple[str, str], MatchScore],
) -> str:
    evidence_rows = sum(len(s.evidence) for s in scores.values())
    lines = [
        "# nightshift — the match score, pinned",
        "#",
        f"# ruleset_version: {ruleset_version()}",
        f"# as_of: {AS_OF.isoformat()}",
        f"# corpus: {len(corpus)} postings x {len(profiles)} profiles"
        f" = {len(scores)} scores, {evidence_rows} evidence rows",
        "#",
        "# Generated. Regenerate with:",
        "#   NIGHTSHIFT_UPDATE_GOLDEN=1 pytest tests/test_matching_golden.py",
        "#",
        "# Regeneration refuses to rewrite a score that already exists here while",
        "# ruleset_version stays the same. If it refuses, that is the point: bump",
        "# RULESET_LOGIC_VERSION when a rule changed, or data/matching.yaml's",
        "# version when a number did, and run it again.",
        "",
    ]
    for entry in corpus:
        for profile_name, _ in profiles:
            lines.extend(_render_score(entry.key, profile_name, scores[entry.key, profile_name]))
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def _blocks(document: str) -> dict[str, str]:
    """Split a rendered golden into `"key · profile" -> block`, headers dropped."""
    blocks: dict[str, str] = {}
    for chunk in document.split("\n\n"):
        block = chunk.strip("\n")
        if not block or block.startswith("#"):
            continue
        blocks[block.split("\n", 1)[0]] = block
    return blocks


def refuse_unbumped(old: str, new: str) -> None:
    """Raise if a score present in both moved while the version did not.

    A *new* score is allowed through unchanged-version: adding a posting to the
    corpus changes no existing score, and refusing it would mean the only way to
    grow the corpus is a version bump that describes nothing — which is how a
    guard gets a reputation for crying wolf and then gets bypassed.
    """
    if _header(old, "ruleset_version") != _header(new, "ruleset_version"):
        return
    before, after = _blocks(old), _blocks(new)
    moved = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    if not moved:
        return
    sample = "\n".join(
        "\n".join(difflib.unified_diff(before[k].split("\n"), after[k].split("\n"), lineterm=""))
        for k in moved[:3]
    )
    raise GoldenRefusedError(
        f"{len(moved)} score(s) changed while ruleset_version stayed "
        f"{_header(new, 'ruleset_version')!r}.\n"
        "A rule moved and the version did not, so every stored result would "
        "claim a ruleset that never produced it. Bump RULESET_LOGIC_VERSION "
        "(a rule changed) or data/matching.yaml's version (a number changed).\n"
        f"First moved: {moved[:3]}\n{sample}"
    )


def _header(document: str, field: str) -> str | None:
    for line in document.split("\n"):
        if line.startswith(f"# {field}:"):
            return line.split(":", 1)[1].strip()
        if not line.startswith("#"):
            break
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _score_everything(corpus: tuple[CorpusPosting, ...] | None = None) -> dict[str, Any]:
    """One full run: load the corpus, load the profiles, score every pair.

    `corpus` is an escape hatch for callers that already have it — everything
    except the determinism test, which passes nothing on purpose.
    """
    corpus = corpus if corpus is not None else load_corpus()
    profiles = load_profiles()
    weights = load_weights()
    scores = {
        (entry.key, name): score_match(entry.posting, profile, weights=weights, as_of=AS_OF)
        for entry in corpus
        for name, profile in profiles
    }
    return {
        "corpus": corpus,
        "profiles": profiles,
        "scores": scores,
        "document": render_golden(corpus, profiles, scores),
    }


@pytest.fixture(scope="module")
def scored(scoring_corpus: tuple[CorpusPosting, ...]) -> dict[str, Any]:
    return _score_everything(scoring_corpus)


# ---------------------------------------------------------------------------
# The golden file itself
# ---------------------------------------------------------------------------


def test_the_scorer_still_produces_the_committed_golden_file(scored: dict[str, Any]) -> None:
    """§4.2. A rule change lands here as a diff somebody has to accept."""
    document: str = scored["document"]

    if UPDATE:
        if GOLDEN_FILE.exists():
            refuse_unbumped(GOLDEN_FILE.read_text(encoding="utf-8"), document)
        GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(document, encoding="utf-8")
        pytest.skip(f"regenerated {GOLDEN_FILE.name}; re-run without the env var")

    assert GOLDEN_FILE.exists(), (
        f"{GOLDEN_FILE} is missing. Generate it with "
        "NIGHTSHIFT_UPDATE_GOLDEN=1 pytest tests/test_matching_golden.py"
    )
    committed = GOLDEN_FILE.read_text(encoding="utf-8")
    if committed != document:
        diff = "\n".join(
            difflib.unified_diff(
                committed.split("\n"),
                document.split("\n"),
                fromfile="committed",
                tofile="computed",
                lineterm="",
                n=2,
            )
        )
        pytest.fail(f"the score moved:\n{diff[:8000]}")


def test_the_golden_file_records_the_ruleset_version_that_produced_it() -> None:
    """A file whose header names a version the code no longer has is a file
    describing rules nobody can reproduce."""
    committed = GOLDEN_FILE.read_text(encoding="utf-8")

    assert _header(committed, "ruleset_version") == ruleset_version()


def test_two_full_runs_are_byte_identical(scored: dict[str, Any]) -> None:
    """§8's determinism assertion, and M3's acceptance criterion.

    Recomputed from scratch — corpus reloaded, requirements re-extracted, every
    pair rescored — rather than compared against the fixture's cached document.
    A second read of the same string proves nothing.
    """
    assert _score_everything()["document"] == scored["document"]


# ---------------------------------------------------------------------------
# The guard, shown able to fail
# ---------------------------------------------------------------------------

_OLD = "# ruleset_version: 1+2026-08-09.1\n\nacme/1 · dev\n  50/100  skill 30 · role 20\n"
_NEW_SAME_VERSION = (
    "# ruleset_version: 1+2026-08-09.1\n\nacme/1 · dev\n  40/100  skill 20 · role 20\n"
)
_NEW_BUMPED = "# ruleset_version: 2+2026-08-09.1\n\nacme/1 · dev\n  40/100  skill 20 · role 20\n"
_OLD_PLUS_A_POSTING = _OLD + "\nacme/2 · dev\n  10/100  skill 10 · role 0\n"


def test_a_score_that_moved_without_a_version_bump_is_refused() -> None:
    """The failure this whole file exists to make impossible: change a rule, see
    red, regenerate, commit — and leave every stored row claiming a ruleset that
    never produced it."""
    with pytest.raises(GoldenRefusedError, match="1 score"):
        refuse_unbumped(_OLD, _NEW_SAME_VERSION)


def test_the_refusal_names_what_moved() -> None:
    """A guard that says only "no" gets bypassed. It has to show the diff."""
    with pytest.raises(GoldenRefusedError) as raised:
        refuse_unbumped(_OLD, _NEW_SAME_VERSION)

    assert "acme/1 · dev" in str(raised.value)
    assert "skill 30" in str(raised.value)
    assert "skill 20" in str(raised.value)


def test_the_same_score_under_the_same_version_is_not_refused() -> None:
    refuse_unbumped(_OLD, _OLD)


def test_a_bumped_version_may_move_every_score() -> None:
    """Which is the whole purpose of bumping it."""
    refuse_unbumped(_OLD, _NEW_BUMPED)


def test_growing_the_corpus_is_not_a_rule_change() -> None:
    """A new posting changes no existing score. Refusing it would make the only
    way to add a fixture a version bump describing nothing, and a guard that
    fires on innocent changes is a guard people learn to route around."""
    refuse_unbumped(_OLD, _OLD_PLUS_A_POSTING)


# ---------------------------------------------------------------------------
# What the golden file would still pass while being worthless
# ---------------------------------------------------------------------------


def test_the_corpus_reaches_more_than_one_score_and_more_than_one_denominator(
    scored: dict[str, Any],
) -> None:
    """The anti-vacuity guard, and the one this project has learned to write.

    A scorer returning 50 for everything satisfies every other assertion in this
    file: it is deterministic, it decomposes, its spans are real, and its golden
    file is byte-stable. M3b's `test_the_corpus_actually_exercises_the_gate` is
    the same guard one milestone up, and it exists because a gate answering
    `uncertain` to everything has perfect precision and is worthless.

    The denominator half is Q6's: if every posting were scored out of 100, the
    assessability distinction would be costing complexity and buying nothing.
    """
    scores: dict[tuple[str, str], MatchScore] = scored["scores"]
    overalls = {s.overall for s in scores.values()}
    denominators = {s.assessed_out_of for s in scores.values()}

    assert len(overalls) >= 10, sorted(overalls)
    assert len(denominators) >= 3, sorted(denominators)
    # Every component earns points somewhere in the corpus. A component that
    # never scores is a rule nothing exercises, which Task 7 would then "prove"
    # load-bearing against a corpus that cannot tell.
    scoring_components = {
        c.component for s in scores.values() for c in s.components if c.points > 0
    }
    assert scoring_components == set(MatchComponent), sorted(
        set(MatchComponent) - scoring_components
    )


def test_at_least_one_pair_could_not_be_assessed_at_all(scored: dict[str, Any]) -> None:
    """`fraction is None` is a real branch, not a defensive one.

    Five (posting, profile) pairs in this corpus reach it — a profile stating
    nothing against a posting with no readable level, no publication date and no
    named technology. If this ever hits zero the branch is untested and the
    honest move is to say so rather than to delete it.
    """
    scores: dict[tuple[str, str], MatchScore] = scored["scores"]

    unscorable = [k for k, s in scores.items() if s.fraction is None]

    assert unscorable, "no pair reaches assessed_out_of == 0; the branch is now untested"
    assert all(scores[k].overall == 0 for k in unscorable)


def test_every_job_span_quotes_the_posting_at_the_offsets_it_claims(
    scored: dict[str, Any],
) -> None:
    """§7.2's first equality, and it must be zero rather than small.

    The database enforces this for stored rows against `description_text`; here
    it also covers `title`, which the trigger cannot see because role relevance
    is the one component decided on a title. An offset that is off by one is a
    quotation of words the posting does not contain, which is the exact shape of
    a fabricated claim.
    """
    corpus: tuple[CorpusPosting, ...] = scored["corpus"]
    postings = {entry.key: entry.posting for entry in corpus}
    scores: dict[tuple[str, str], MatchScore] = scored["scores"]

    wrong: list[str] = []
    checked = 0
    for (key, profile_name), score in scores.items():
        posting = postings[key]
        for row in score.evidence:
            if row.job_span_text is None:
                continue
            checked += 1
            source = posting.title if row.job_span_field == "title" else posting.description_text
            if source[row.job_char_start : row.job_char_end] != row.job_span_text:
                wrong.append(f"{key}/{profile_name} {row.component}: {row.job_span_text!r}")

    assert checked > 100, f"only {checked} spans checked; the corpus stopped producing them"
    assert wrong == []
