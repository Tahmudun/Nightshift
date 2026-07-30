"""Company name normalization.

``normalized_name`` is a unique column, so this function decides employer
identity. It can fail in two directions and both matter: too aggressive splits
one company into two, too lax merges two real companies into one.

The tests are organised around those two failure directions rather than around
the implementation, because that is what a reviewer needs to check.
"""

from __future__ import annotations

import pytest

from citysignal.domain.companies import normalize_company_name


class TestMergesWhatShouldMerge:
    @pytest.mark.parametrize(
        "variants",
        [
            ("Datadog", "Datadog, Inc.", "DATADOG INC", "datadog inc."),
            ("Stripe", "Stripe, Inc.", "  Stripe  "),
            ("Acme Co Ltd", "Acme"),
            ("Zalando SE", "Zalando SE"),
        ],
    )
    def test_variants_of_one_company_share_a_key(self, variants: tuple[str, ...]) -> None:
        keys = {normalize_company_name(name) for name in variants}
        assert len(keys) == 1, f"{variants} produced {keys}"

    def test_accents_do_not_create_a_second_company(self) -> None:
        assert normalize_company_name("Société Générale") == normalize_company_name(
            "Societe Generale"
        )

    @pytest.mark.parametrize(
        "with_apostrophe,without",
        [
            ("Moody's Analytics", "Moodys Analytics"),
            ("Macy's", "Macys"),
            # A typographic apostrophe must behave like a typewriter one.
            ("Moody’s", "Moodys"),  # noqa: RUF001
        ],
    )
    def test_an_apostrophe_does_not_split_a_company(
        self, with_apostrophe: str, without: str
    ) -> None:
        """Deleted, not spaced: "Moody's" -> "moody s" would not match "Moodys"."""
        assert normalize_company_name(with_apostrophe) == normalize_company_name(without)

    def test_ampersand_becomes_a_separator_not_a_word(self) -> None:
        """The contract is "drop punctuation", not "spell out symbols"."""
        assert normalize_company_name("Ben & Jerry's") == "ben jerrys"


class TestKeepsSeparateWhatShouldStaySeparate:
    @pytest.mark.parametrize(
        "left,right",
        [
            # The classic false merge a fuzzy matcher would make.
            ("Meta", "Metabase"),
            ("Ramp", "Rampart"),
            ("Notion", "Notional"),
            # Suffixes that distinguish real companies are NOT stripped.
            ("Palantir Technologies", "Palantir"),
            ("Two Sigma", "Two Sigma Investments"),
            ("Bloomberg", "Bloomberg Industry Group"),
            ("Datadog", "Datadog Labs"),
        ],
    )
    def test_distinct_companies_get_distinct_keys(self, left: str, right: str) -> None:
        assert normalize_company_name(left) != normalize_company_name(right)

    def test_no_fuzzy_matching_is_performed(self) -> None:
        """A one-character difference must survive. This function is exact-after-
        normalization by design; edit distance belongs nowhere near a unique key."""
        assert normalize_company_name("Stripe") != normalize_company_name("Stripes")


class TestEdgeCases:
    def test_a_suffix_only_name_keeps_its_token(self) -> None:
        """Stripping must never empty the key — it is a unique column."""
        assert normalize_company_name("Inc") == "inc"

    def test_stacked_suffixes_are_stripped(self) -> None:
        assert normalize_company_name("Foo Co Ltd") == "foo"

    def test_internal_whitespace_is_collapsed(self) -> None:
        assert normalize_company_name("Two   Sigma") == "two sigma"

    @pytest.mark.parametrize("name", ["", "   ", ",,,", "...", "&"])
    def test_an_unnameable_company_raises_rather_than_returning_empty(self, name: str) -> None:
        """An empty key would collide every unnameable company into one row."""
        with pytest.raises(ValueError, match="normalizes to nothing"):
            normalize_company_name(name)

    def test_is_deterministic(self) -> None:
        assert normalize_company_name("Datadog, Inc.") == normalize_company_name("Datadog, Inc.")

    def test_is_idempotent(self) -> None:
        once = normalize_company_name("Datadog, Inc.")
        assert normalize_company_name(once) == once
