"""The vocabulary, and the precision rules that keep it from matching prose."""

from __future__ import annotations

import pytest

from nightshift.domain.skill_vocabulary import load_vocabulary, parse_vocabulary

VOCABULARY = load_vocabulary()


def test_the_file_declares_a_version() -> None:
    assert VOCABULARY.version


def test_a_term_matches_and_reports_where_it_was_found() -> None:
    text = "Languages: Python, TypeScript"
    matches = {match.canonical_name: match for match in VOCABULARY.match(text)}
    assert set(matches) == {"Python", "TypeScript"}
    found = matches["Python"]
    assert text[found.char_start : found.char_end] == "Python"


def test_an_alias_resolves_to_its_canonical_name_and_quotes_the_alias() -> None:
    text = "Built the API in Golang."
    (match,) = [m for m in VOCABULARY.match(text) if m.canonical_name == "Go"]
    assert text[match.char_start : match.char_end] == "Golang"


def test_a_term_inside_a_longer_word_is_not_a_match() -> None:
    """github.com is not the skill Git, and javascriptural is not JavaScript."""
    assert VOCABULARY.match("see github.com/example for javascriptural notes") == []


@pytest.mark.parametrize(
    "prose",
    [
        "I go to class every morning",
        "there was some rust on the railing",
        "we express our findings clearly",
        "I excel at working with others",
    ],
)
def test_ordinary_english_does_not_become_a_skill(prose: str) -> None:
    assert VOCABULARY.match(prose) == []


def test_the_longest_term_wins_when_two_overlap() -> None:
    """ "Tailwind CSS" is one skill, not "Tailwind" plus "CSS".

    The first version of this test used "Machine Learning" and **could not
    fail**: no shorter vocabulary term appears inside that phrase, so the
    longest-first ordering it claimed to guard was never exercised. Caught by
    mutating the sort and watching nothing go red. Three vocabulary terms
    overlap in this phrase — `Tailwind CSS`, `tailwind` and `CSS` — so it does.
    """
    text = "Styling: Tailwind CSS"
    matches = VOCABULARY.match(text)
    assert [m.canonical_name for m in matches] == ["Tailwind CSS"]
    assert text[matches[0].char_start : matches[0].char_end] == "Tailwind CSS"


def test_a_repeated_skill_is_proposed_once_at_its_first_appearance() -> None:
    text = "Python at work. Python at home."
    (match,) = VOCABULARY.match(text)
    assert match.canonical_name == "Python"
    assert match.char_start == 0


def test_matches_come_back_in_the_order_they_appear() -> None:
    text = "Docker, then Python, then Redis"
    positions = [match.char_start for match in VOCABULARY.match(text)]
    assert positions == sorted(positions)


def test_matching_the_same_text_twice_gives_the_same_answer() -> None:
    text = "Python, Docker, Python again"
    assert VOCABULARY.match(text) == VOCABULARY.match(text)


def test_a_name_with_punctuation_still_matches() -> None:
    """`\\b` cannot do this: there is no word boundary after `+`."""
    text = "Languages: C++, C#"
    found = {match.canonical_name for match in VOCABULARY.match(text)}
    assert found == {"C++", "C#"}


def test_a_one_character_skill_must_declare_both_overrides() -> None:
    """ "R" is a language; "r" is a letter. The loader refuses the sloppy form."""
    from nightshift.domain.skill_vocabulary import parse_vocabulary

    with pytest.raises(ValueError, match="case-sensitive"):
        parse_vocabulary(
            {
                "version": "test",
                "skills": [{"name": "R", "minimum_length_override": True}],
            }
        )


def test_every_canonical_name_is_clean() -> None:
    """A stray space in the YAML is a skill nobody can ever match."""
    for name in VOCABULARY.canonical_names:
        assert name.strip() == name and name


def test_match_all_keeps_every_occurrence_and_match_keeps_one() -> None:
    """The distinction the requirement extractor depends on."""
    vocab = load_vocabulary()
    text = "We are a Python shop. REQUIREMENTS Proficiency in Python."
    assert len(vocab.match(text)) == 1
    both = [m for m in vocab.match_all(text) if m.canonical_name == "Python"]
    assert len(both) == 2
    assert both[0].char_start < both[1].char_start


def test_match_all_still_refuses_overlapping_terms() -> None:
    """ "Tailwind CSS" must not also yield a bare "CSS" inside it."""
    vocab = load_vocabulary()
    names = [m.canonical_name for m in vocab.match_all("We use Tailwind CSS here.")]
    assert names == ["Tailwind CSS"]


def test_every_match_all_span_quotes_the_text() -> None:
    vocab = load_vocabulary()
    text = "REQUIREMENTS Python, Kotlin, and Rust. NICE TO HAVES Python."
    for m in vocab.match_all(text):
        assert text[m.char_start : m.char_end].casefold() != ""


# -- demonstrated_by: the ontology edge ADR 0018 recommends ------------------


def test_a_concept_carries_the_tools_that_demonstrate_it() -> None:
    """ADR 0018's edge: PyTorch really is evidence of machine learning.

    One-directional and narrow on purpose. It says a tool demonstrates a
    concept, never that one tool demonstrates another.
    """
    vocab = parse_vocabulary(
        {
            "version": "test",
            "skills": [
                {"name": "PyTorch"},
                {"name": "TensorFlow"},
                {"name": "Machine Learning", "demonstrated_by": ["PyTorch", "TensorFlow"]},
            ],
        }
    )
    assert vocab.demonstrated_by("Machine Learning") == ("PyTorch", "TensorFlow")
    assert vocab.demonstrated_by("PyTorch") == ()


def test_a_tool_that_is_not_in_the_vocabulary_is_refused() -> None:
    """A typo'd tool name demonstrates nothing and says nothing while doing it.

    Without this the edge is silently dead: the concept keeps its list, no
    confirmed skill ever resolves through it, and every test stays green.
    """
    with pytest.raises(ValueError, match="Pytorch"):
        parse_vocabulary(
            {
                "version": "test",
                "skills": [
                    {"name": "PyTorch"},
                    {"name": "Machine Learning", "demonstrated_by": ["Pytorch"]},
                ],
            }
        )


def test_a_concept_cannot_demonstrate_itself() -> None:
    with pytest.raises(ValueError, match="itself"):
        parse_vocabulary(
            {
                "version": "test",
                "skills": [{"name": "Machine Learning", "demonstrated_by": ["Machine Learning"]}],
            }
        )
