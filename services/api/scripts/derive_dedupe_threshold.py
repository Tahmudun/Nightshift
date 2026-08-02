"""Derive the similarity threshold from the labelled dedupe fixture set.

ADR 0010: the threshold is not chosen by taste. This prints every labelled
pair's cosine similarity under the real model, then reports the gap between the
lowest `merge` pair and the highest `distinct` pair — the window any honest
threshold has to sit in.

If no such window exists, it says so and refuses to suggest a number. A
threshold that does not separate the labelled set is a threshold with no
evidence behind it, and picking one anyway is the guessing this project forbids
everywhere else.

Run: `cd services/api && ./.venv/bin/python scripts/derive_dedupe_threshold.py`
"""

from __future__ import annotations

from pathlib import Path

import yaml

from nightshift.domain.embeddings import cosine_similarity, default_embedder

FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "dedupe_pairs.yaml"


def main() -> None:
    cases = yaml.safe_load(FIXTURE.read_text())["cases"]
    embedder = default_embedder()

    scored: list[tuple[float, str, str]] = []
    for case in cases:
        a, b = case["a"], case["b"]
        if not a.get("description") or not b.get("description"):
            # Pairs without descriptions never reach the similarity layer, so
            # they say nothing about where the threshold belongs.
            continue
        vector_a, vector_b = embedder.embed([a["description"], b["description"]])
        scored.append((cosine_similarity(vector_a, vector_b), case["verdict"], case["name"]))

    scored.sort(reverse=True)
    print(f"{'similarity':>10}  {'verdict':<9}  case")
    for score, verdict, name in scored:
        print(f"{score:>10.4f}  {verdict:<9}  {name}")

    merges = [score for score, verdict, _ in scored if verdict == "merge"]
    distincts = [score for score, verdict, _ in scored if verdict == "distinct"]
    if not merges or not distincts:
        print("\nnot enough labelled pairs with descriptions to derive a threshold")
        return

    lowest_merge, highest_distinct = min(merges), max(distincts)
    print(f"\nlowest  merge    : {lowest_merge:.4f}")
    print(f"highest distinct : {highest_distinct:.4f}")

    if lowest_merge <= highest_distinct:
        print(
            "\nNO SEPARATING THRESHOLD EXISTS.\n"
            "Do not pick a number that splits the difference. Record this, and "
            "either strengthen the deterministic layers or accept that these "
            "pairs are not separable by description similarity alone."
        )
        return

    print(f"\nany threshold in ({highest_distinct:.4f}, {lowest_merge:.4f}] separates the set")
    print(f"margin: {lowest_merge - highest_distinct:.4f}")
    print(f"suggested (midpoint, rounded down to 2dp): {(lowest_merge + highest_distinct) / 2:.2f}")


if __name__ == "__main__":
    main()
