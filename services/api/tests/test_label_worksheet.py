"""The worksheet generator.

The excerpt is the only part of a posting a human will read, so a bug here does
not produce a wrong label — it produces a label made from the wrong evidence,
which is worse because it looks identical.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def worksheet() -> Any:
    spec = importlib.util.spec_from_file_location(
        "make_label_worksheet", ROOT / "scripts" / "make_label_worksheet.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_label_worksheet"] = module
    spec.loader.exec_module(module)
    return module


def test_the_excerpt_starts_at_the_requirements_heading(worksheet: Any) -> None:
    text = (
        "ABOUT US We are a company. " * 20
        + "WHAT YOU'LL NEED Proficiency in Kotlin. "
        + "NICE TO HAVES Experience with React."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("WHAT YOU'LL NEED")
    assert "Proficiency in Kotlin" in excerpt


def test_the_excerpt_keeps_the_preferred_section(worksheet: Any) -> None:
    """The nice-to-have section is the single most important thing to label.

    An excerpt that stops at the required list would produce an answer key with
    an empty `mentioned_not_required` for every posting, and that field is the
    difference between a usable product and one that reports nine false gaps.
    """
    text = "WHAT YOU'LL NEED Kotlin. NICE TO HAVES React, TypeScript, Flask."
    excerpt = worksheet.requirements_excerpt(text)
    assert "NICE TO HAVES" in excerpt
    assert "Flask" in excerpt


def test_a_short_text_with_no_heading_is_returned_whole_but_marked(
    worksheet: Any,
) -> None:
    """Marked even though it is short.

    Akuna's "Talent Community" blurb is 523 characters with no requirements at
    all. Unmarked, it reads as though the blurb *is* the requirements — the
    same failure as a bad anchor, at a smaller size.
    """
    text = "We want someone who can write Kotlin and has shipped an app."
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt == worksheet.NO_HEADING_WHOLE + text
    assert excerpt.startswith(worksheet.NO_HEADING_PREFIX)


def test_a_long_text_with_no_heading_returns_a_marked_tail(worksheet: Any) -> None:
    """Never the whole document. The first version produced 8,000-character
    excerpts, and an unmarked fallback reads as evidence rather than a guess."""
    text = "Company blurb. " * 400 + "You will write Kotlin."
    excerpt = worksheet.requirements_excerpt(text, window=200)
    assert excerpt.startswith(worksheet.NO_HEADING_TAIL)
    assert "You will write Kotlin." in excerpt
    assert len(excerpt) <= 200 + len(worksheet.NO_HEADING_TAIL)


def test_a_heading_word_inside_prose_is_not_an_anchor(worksheet: Any) -> None:
    """The exact compensation boilerplate that broke 16 Akuna postings.

    "qualifications" appears mid-clause. Anchoring there shows a labeler a pay
    disclaimer and none of the posting's requirements.
    """
    text = (
        "The base salary depends on experience, qualifications, and skill set. "
        "This role is also eligible for a discretionary bonus. "
        "Qualities that make great candidates: Graduating between 2027 and 2028."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("Qualities that make great candidates")


def test_a_duty_containing_a_heading_word_is_not_an_anchor(worksheet: Any) -> None:
    """ "meet regulatory requirements by translating..." is a job duty."""
    text = (
        "You will meet regulatory requirements by translating commitments into "
        "engineering work. WHAT YOU'LL NEED Proficiency in Kotlin."
    )
    assert worksheet.requirements_excerpt(text).startswith("WHAT YOU'LL NEED")


def test_a_capitalised_heading_anchors_even_without_a_colon(worksheet: Any) -> None:
    text = "About us we are great. WHAT YOU'LL NEED Proficiency in Kotlin."
    assert worksheet.requirements_excerpt(text).startswith("WHAT YOU'LL NEED")


def test_every_selected_excerpt_starts_at_a_heading_or_says_it_could_not(
    worksheet: Any,
) -> None:
    """The property that failed on the first real run: 30 of 60 broken.

    Runs over the actual corpus rather than invented strings, because the
    failure was invisible to every invented string in this file.

    Stated as "starts at a known heading" rather than the first version's
    "does not start with a lowercase letter". That heuristic was a proxy for
    anchoring mid-prose, and once `_heading_positions` got strict the proxy
    started firing on genuine lowercase headings — several boards write
    ``you have:`` in sentence case. Five real headings were being reported as
    defects. The property below is what the proxy was reaching for.
    """
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if excerpt.startswith(worksheet.NO_HEADING_PREFIX):
            continue
        lowered = excerpt.casefold()
        if not any(lowered.startswith(h) for h in worksheet._REQUIREMENT_HEADINGS):
            offenders.append(f"{board}/{posting['id']}: {excerpt[:70]}")
    assert offenders == [], f"{len(offenders)} excerpts anchored off-heading"


def test_no_selected_excerpt_is_a_wall_of_text(worksheet: Any) -> None:
    """13 of the first 60 ran past 1,500 characters; one hit 8,019.

    The bound tracks the window rather than being a separate number. It was
    literally 1400 for several rounds and went stale the moment the window rose
    to 2500 — a guard whose threshold has to be remembered separately is a
    guard that will disagree with the code it guards.
    """
    limit = 2500 + len(worksheet.TRUNCATED_SUFFIX)
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if len(excerpt) > limit:
            offenders.append(f"{board}/{posting['id']}: {len(excerpt)} chars")
    assert offenders == [], f"{len(offenders)} excerpts too long: {offenders[:5]}"


def test_most_selected_excerpts_find_a_real_heading(worksheet: Any) -> None:
    """The fallback is honest, but it is still a fallback.

    Two things keep this number down and they fail differently. If
    `_REQUIREMENT_HEADINGS` is missing vocabulary these boards use, the fix is
    to add it. If selection stops preferring excerptable postings, the fix is
    there. Either way a person is reading boilerplate instead of requirements.
    """
    picked = worksheet.select_for_labeling(worksheet._all_postings())
    fell_back = sum(
        worksheet.requirements_excerpt(p["text"]).startswith(worksheet.NO_HEADING_PREFIX)
        for _, p in picked
    )
    assert fell_back <= len(picked) // 10, (
        f"{fell_back} of {len(picked)} excerpts had no heading to anchor on"
    )


def test_a_distinctive_heading_needs_no_further_proof(worksheet: Any) -> None:
    """Three real postings fell back because these were made to prove themselves.

    "You might thrive in this role if you:" (OpenAI), "You may be a good fit if
    you have:" (Anthropic) and a bare "Minimum qualifications" line all failed
    the colon-and-capitals test — the vocabulary stores stems, so the colon sat
    a clause away, and HTML flattening had removed the punctuation before them.
    """
    for text, expected in (
        ("About us. You might thrive in this role if you: Kotlin.", "you might thrive"),
        ("About us. You may be a good fit if you have: Kotlin.", "you may be a good fit"),
        ("About us blurb Minimum qualifications 3 years of Python.", "minimum qualifications"),
    ):
        assert worksheet.requirements_excerpt(text).casefold().startswith(expected), text


def test_an_ambiguous_heading_still_has_to_prove_itself(worksheet: Any) -> None:
    """The prose-anchoring bug must not come back through the new branch."""
    text = (
        "The base salary depends on experience, qualifications, and skill set. "
        "You will meet regulatory requirements by translating commitments. "
        "WHAT YOU'LL NEED Proficiency in Kotlin."
    )
    assert worksheet.requirements_excerpt(text).startswith("WHAT YOU'LL NEED")


def test_a_colon_after_a_sentence_terminator_does_not_count(worksheet: Any) -> None:
    """`_colon_follows` must abandon the search at the end of the sentence."""
    assert worksheet._colon_follows("qualifications, and skill set. Note: x", 0) is False
    assert worksheet._colon_follows(" in this role if you: Kotlin", 0) is True


def test_the_excerpt_stops_at_the_next_non_requirements_section(
    worksheet: Any,
) -> None:
    """Pay disclaimers and benefits are not requirements and must not appear."""
    text = (
        "REQUIREMENTS Proficiency in Kotlin. "
        + "More real requirements here. " * 8
        + "COMPENSATION The base salary range for this role is $200,000 to $300,000 "
        "and this role is also eligible for a discretionary bonus."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert "Proficiency in Kotlin" in excerpt
    assert "$200,000" not in excerpt
    assert "discretionary bonus" not in excerpt


def test_a_section_ended_by_a_closer_is_not_marked_as_cut(worksheet: Any) -> None:
    """Stopping at the section's own end is completeness, not truncation.

    Marking it would put the notice on almost every posting and teach a labeler
    to ignore it — which is what a 1200-char window with no boundary did, at
    56 of 60.
    """
    text = "REQUIREMENTS Kotlin. " + "Real requirement. " * 12 + "BENEFITS Free lunch."
    excerpt = worksheet.requirements_excerpt(text)
    assert not excerpt.endswith(worksheet.TRUNCATED_SUFFIX)
    assert "Free lunch" not in excerpt


def test_a_closer_word_inside_a_bullet_does_not_end_the_section(
    worksheet: Any,
) -> None:
    """OpenAI's "Account Director - Tokyo", found by reading the worksheet.

    "benefits" appears inside a requirement bullet. A bare match there ended
    the section three requirements early and showed no truncation marker,
    because as far as the code knew the section had simply ended. An excerpt
    that stops *before* the requirements is worse than one that runs past them,
    and it is indistinguishable from a complete one.
    """
    text = (
        "REQUIREMENTS Proficiency in Kotlin. "
        "Experience selling benefits software to enterprise customers. "
        "Familiarity with Rust and Python. " + "More requirements here. " * 6
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert "Familiarity with Rust and Python" in excerpt


def test_no_excerpt_silently_drops_eligibility_content(worksheet: Any) -> None:
    """The guard that caught the worst defect on this task, kept permanently.

    Every other check here asks whether the excerpt *looks* right: does it
    start at a heading, is it short enough, is it marked when cut. None of them
    can see the failure that matters most — an excerpt that ends cleanly,
    carries no marker, and has dropped a requirement the labeler is being asked
    to record.

    That is not hypothetical. Closing Anthropic's sections at `Logistics` cut
    "Minimum education: Bachelor's degree or an equivalent combination of
    education and experience" from twelve postings, and closing at
    `Location-based hybrid` cut "Visa sponsorship: We do sponsor visas!". Both
    are among the nine fields being labeled. Every test passed.

    An excerpt may end early only if what follows is genuinely boilerplate. If
    the dropped text still reads like requirements, either the closer is wrong
    or the excerpt should have been marked as cut.
    """
    import re as _re

    eligibility_language = _re.compile(
        r"\b(years? of|degree|bachelor|master'?s|phd|proficien|graduat|enrolled"
        r"|sponsor|work authoriz|minimum education|experience (with|in))\b",
        _re.I,
    )
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if excerpt.startswith(worksheet.NO_HEADING_PREFIX):
            continue
        if excerpt.endswith(worksheet.TRUNCATED_SUFFIX):
            continue  # marked, so the labeler knows to open the fixture
        positions = worksheet._heading_positions(posting["text"])
        body = posting["text"][positions[0] :]
        dropped = body[worksheet._section_end(body) :]
        hits = eligibility_language.findall(dropped[:1200])
        if len(hits) >= 3:
            offenders.append(f"{board}/{posting['id']}: dropped {dropped[:70]!r}")
    assert offenders == [], (
        f"{len(offenders)} excerpts ended cleanly while dropping eligibility "
        f"content: {offenders[:3]}"
    )


def test_no_section_ends_almost_immediately(worksheet: Any) -> None:
    """A closer firing just after the heading would hide everything.

    The counterpart to the wall-of-text guard, and the failure mode that
    adding closers risks: each new closer is a new chance to end a section
    early, and an excerpt that stops at once looks tidy rather than broken.
    """
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if excerpt.startswith(worksheet.NO_HEADING_PREFIX):
            continue
        if len(excerpt) < 300:
            offenders.append(f"{board}/{posting['id']}: {len(excerpt)} chars — {excerpt[:60]}")
    assert len(offenders) <= 1, f"{len(offenders)} excerpts end almost at once: {offenders}"


def test_a_capitalised_closer_still_ends_the_section(worksheet: Any) -> None:
    """The bullet rule must not stop real closers working."""
    text = "REQUIREMENTS Kotlin. " + "Real requirement. " * 10 + "BENEFITS Free lunch."
    assert "Free lunch" not in worksheet.requirements_excerpt(text)


def test_the_required_section_wins_over_a_later_optional_one(
    worksheet: Any,
) -> None:
    """Two Jump postings showed "Bonus Points" while the required list above it
    went unshown, which made `required_tech` unanswerable from the worksheet."""
    text = "About us. Skills You'll Need: Kotlin and Rust. Bonus Points: Experience with CUDA."
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("Skills You'll Need")
    assert "Kotlin and Rust" in excerpt


def test_a_closer_inside_the_heading_line_does_not_end_the_section(
    worksheet: Any,
) -> None:
    """`_CLOSER_OFFSET` exists because flattened HTML can put a requirements
    heading and the word "compensation" within a sentence of each other."""
    text = (
        "REQUIREMENTS Experience with compensation systems. Proficiency in Kotlin. "
        + "More requirements. " * 8
    )
    assert "Proficiency in Kotlin" in worksheet.requirements_excerpt(text)


def test_most_selected_excerpts_are_not_cut_off(worksheet: Any) -> None:
    """A marker on almost every posting is a marker nobody reads.

    Measured at 56 of 60 before the section boundary existed. If this rises
    again the fix is the closer list or the window, and the docstring on
    `_SECTION_CLOSERS` records the measurements to decide which.
    """
    picked = worksheet.select_for_labeling(worksheet._all_postings())
    cut = sum(
        worksheet.requirements_excerpt(p["text"]).endswith(worksheet.TRUNCATED_SUFFIX)
        for _, p in picked
    )
    assert cut <= len(picked) // 4, f"{cut} of {len(picked)} excerpts cut off"


def test_a_cut_off_excerpt_says_so(worksheet: Any) -> None:
    """Akuna's "Security Engineer II" lost TCP/IP, DNS, HTTP/S and VPNs to the
    window with no signal. A labeler would under-report `required_tech` and
    have no way to know they were reading a fragment."""
    text = "REQUIREMENTS " + "Python and Kotlin and Rust. " * 200
    excerpt = worksheet.requirements_excerpt(text, window=100)
    assert excerpt.endswith(worksheet.TRUNCATED_SUFFIX)


def test_an_excerpt_that_reaches_the_end_does_not_claim_to_be_cut(
    worksheet: Any,
) -> None:
    text = "REQUIREMENTS Proficiency in Kotlin."
    assert not worksheet.requirements_excerpt(text).endswith(worksheet.TRUNCATED_SUFFIX)


def test_no_known_heading_is_present_but_undetected(worksheet: Any) -> None:
    """The gap none of the corpus-wide tests could see.

    The existing guards ask "did we find *a* heading" and "is the fallback
    count under budget". Neither asks the question that mattered: is a heading
    phrase sitting in the raw text that we failed to detect? Three postings
    fell back with a known heading present, and every test passed.
    """
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        text = posting["text"]
        if worksheet._heading_positions(text):
            continue
        lowered = text.casefold()
        present = [h for h in worksheet._REQUIREMENT_HEADINGS if h in lowered]
        if present:
            offenders.append(f"{board}/{posting['id']}: undetected {present[:3]}")
    assert offenders == [], f"{len(offenders)} postings: {offenders}"


def test_regenerating_never_overwrites_a_filled_in_label(
    worksheet: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """The one property protecting ninety minutes of somebody's work.

    Proved by hand after each of four fix rounds and guarded by nothing, which
    is exactly the shape of thing that breaks on the fifth.
    """
    import yaml

    labels = tmp_path / "labels.yaml"
    monkeypatch.setattr(worksheet, "LABELS", labels)
    monkeypatch.setattr(worksheet, "WORKSHEET", tmp_path / "worksheet.md")

    worksheet.main()
    key = yaml.safe_load(labels.read_text())
    board = sorted(key["boards"])[0]
    pid = sorted(key["boards"][board])[0]
    key["boards"][board][pid]["is_internship"] = "no"
    key["boards"][board][pid]["note"] = "checked by hand"
    labels.write_text(yaml.safe_dump(key, sort_keys=True, allow_unicode=True))

    worksheet.main()
    after = yaml.safe_load(labels.read_text())
    assert after["boards"][board][pid]["is_internship"] == "no"
    assert after["boards"][board][pid]["note"] == "checked by hand"


def test_selection_prefers_a_posting_whose_requirements_can_be_shown(
    worksheet: Any,
) -> None:
    """Given two postings under one reason, take the one with a heading."""
    headless = _posting("1", "Engineer A", "internship")
    headless["text"] = "We are a great company with a strong culture. " * 40
    excerptable = _posting("2", "Engineer B", "internship")
    excerptable["text"] = "About us. REQUIREMENTS Proficiency in Kotlin."
    picked = worksheet.select_for_labeling([("b1", headless), ("b1", excerptable)], target=1)
    assert [p["id"] for _, p in picked] == ["2"]


def test_a_reason_with_only_headless_postings_still_contributes(
    worksheet: Any,
) -> None:
    """Preferring excerptable postings must not delete a shape.

    A marked "could not find it" is worse than a real excerpt and far better
    than a missing eligibility shape.
    """
    headless = _posting("1", "Engineer", "doctorate")
    headless["text"] = "We are a great company with a strong culture. " * 40
    picked = worksheet.select_for_labeling([("b1", headless)], target=5)
    assert len(picked) == 1


def _posting(pid: str, title: str, reason: str) -> dict[str, Any]:
    return {"id": pid, "title": title, "reason": reason, "text": "REQUIREMENTS Python."}


def test_selection_covers_every_reason_before_deepening_any(worksheet: Any) -> None:
    """Round-robin across shapes, not the first N in file order.

    Taking postings in file order would hand back sixty postings from three
    boards with whole eligibility shapes missing, and the answer key would be
    blind to exactly the cases A13 calls hard.
    """
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(50)]
    postings += [("b2", _posting("z1", "Researcher", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert "doctorate" in {p["reason"] for _, p in picked}


def test_a_reason_with_one_example_still_contributes(worksheet: Any) -> None:
    """A shape with a single instance is the one most likely to be got wrong."""
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(100)]
    postings += [("b2", _posting("solo", "Research Scientist", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=60)
    assert ("b2", postings[-1][1]) in picked


def test_recruiting_roles_are_skipped_under_the_new_grad_reason(
    worksheet: Any,
) -> None:
    """ "Campus Recruiter" matched the new-grad selector on a real board.

    It is a job recruiting new grads, not a job for one. Labeling it teaches
    the answer key nothing about new-grad eligibility.
    """
    postings = [
        ("b1", _posting("1", "Campus Recruiter", "new grad / university programme")),
        ("b1", _posting("2", "University Recruiter", "new grad / university programme")),
        ("b1", _posting("3", "Software Engineer, New Grad", "new grad / university programme")),
    ]
    picked = worksheet.select_for_labeling(postings, target=3)
    assert [p["title"] for _, p in picked] == ["Software Engineer, New Grad"]


def test_an_immigration_role_is_skipped_under_the_sponsorship_reason(
    worksheet: Any,
) -> None:
    """Jane Street's "Immigration and Mobility Specialist", found on real data.

    It matched on "advise on visa sponsorship considerations during the hiring
    process" — a job administering sponsorship for employees, not a posting
    stating its own policy toward an applicant.
    """
    postings = [
        (
            "b1",
            _posting("1", "Immigration and Mobility Specialist", "sponsorship stated in writing"),
        ),
        ("b1", _posting("2", "Software Engineer", "sponsorship stated in writing")),
    ]
    picked = worksheet.select_for_labeling(postings, target=2)
    assert [p["title"] for _, p in picked] == ["Software Engineer"]


def test_the_skip_is_scoped_to_the_reason_that_earned_it(worksheet: Any) -> None:
    """An immigration specialist is a fine example of a *senior title*.

    Skipping it under every reason would throw away real signal to fix one bad
    annotation.
    """
    postings = [
        (
            "b1",
            _posting("1", "Immigration and Mobility Specialist", "senior or above in the title"),
        ),
    ]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert len(picked) == 1


def test_a_reason_made_entirely_of_recruiting_roles_still_contributes(
    worksheet: Any,
) -> None:
    """Dropping every posting under a reason would delete the shape silently.

    Better a weak example the human can mark odd in `note` than a shape that
    vanishes without appearing anywhere.
    """
    postings = [("b1", _posting("1", "Campus Recruiter", "new grad / university programme"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert len(picked) == 1


def test_selection_is_deterministic(worksheet: Any) -> None:
    """Regenerating must not reshuffle what a human has already worked through."""
    postings = [
        ("b2", _posting("9", "B", "internship")),
        ("b1", _posting("3", "A", "doctorate")),
        ("b1", _posting("1", "C", "internship")),
    ]
    first = worksheet.select_for_labeling(postings, target=3)
    second = worksheet.select_for_labeling(list(reversed(postings)), target=3)
    assert [p["id"] for _, p in first] == [p["id"] for _, p in second]


def test_selection_never_pads_past_the_corpus(worksheet: Any) -> None:
    postings = [("b1", _posting("1", "Engineer", "internship"))]
    assert len(worksheet.select_for_labeling(postings, target=60)) == 1


def test_no_posting_is_selected_twice(worksheet: Any) -> None:
    postings = [("b1", _posting(str(i), f"Engineer {i}", "internship")) for i in range(80)]
    picked = worksheet.select_for_labeling(postings, target=60)
    keys = [(b, p["id"]) for b, p in picked]
    assert len(keys) == len(set(keys)) == 60


def test_a_blank_label_has_every_field_and_no_value(worksheet: Any) -> None:
    label = worksheet.blank_label("abc123", "Software Engineer Internship")
    assert label["title"] == "Software Engineer Internship"
    for field in (
        "is_internship",
        "graduation_window",
        "enrollment_required",
        "degree",
        "min_years_experience",
        "required_tech",
        "mentioned_not_required",
        "sponsorship",
        "note",
    ):
        assert field in label, field
    assert label["is_internship"] == "TO_LABEL"
    assert label["required_tech"] == "TO_LABEL"
