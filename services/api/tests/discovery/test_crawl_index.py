"""Token extraction from a recorded Common Crawl index slice.

The fixture is a real recorded response. Its shape is the whole reason this
module is not a one-line regex: most captured URLs are *job pages beneath* a
board rather than board roots, and they carry tracking parameters. A parser
taking the last path segment would harvest job UUIDs and fill the registry with
boards that do not exist.
"""

from __future__ import annotations

from pathlib import Path

from nightshift.discovery.sources.crawl_index import PROVIDER_PATTERNS, tokens_from_cdx

FIXTURE = Path(__file__).parent.parent / "fixtures" / "crawl" / "ashby_cc_main_2026_30.jsonl"


def _lines() -> list[str]:
    return FIXTURE.read_text().splitlines()


def test_extracts_the_first_path_segment_as_the_token() -> None:
    tokens = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    assert tokens
    assert "0g" in tokens, "the ADR 0005 case is missing; re-record with a higher limit"


def test_never_harvests_a_job_id_as_a_token() -> None:
    """Job pages live beneath the board: jobs.ashbyhq.com/{token}/{uuid}.

    A parser taking the last segment would return the uuid. The length guard is
    deliberately not "no hyphens" — the recorded slice contains real tokens
    like `a-place-for-mom` and `a16z-new-media`, and a hyphen ban would reject
    them while a 36-character UUID is what actually needs rejecting.
    """
    tokens = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    for token in tokens:
        assert len(token) < 36, f"looks like a job id: {token}"
        assert token not in {"application", "api"}


def test_tracking_parameters_do_not_create_duplicate_tokens() -> None:
    lines = [
        '{"url": "https://jobs.ashbyhq.com/acme"}',
        '{"url": "https://jobs.ashbyhq.com/acme?utm_source=x"}',
        '{"url": "https://jobs.ashbyhq.com/acme/1234?ref=y"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["acme"]


def test_a_url_on_another_host_is_ignored() -> None:
    """The pattern is applied server-side, but a pattern can match a host we
    did not mean. The check is ours, not theirs."""
    lines = [
        '{"url": "https://jobs.ashbyhq.com/real"}',
        '{"url": "https://evil.jobs.ashbyhq.com.attacker.test/fake"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["real"]


def test_the_board_root_alone_is_enough() -> None:
    assert tokens_from_cdx(
        ['{"url": "https://jobs.ashbyhq.com/solo"}'], host="jobs.ashbyhq.com"
    ) == ["solo"]


def test_a_bare_host_yields_nothing() -> None:
    """No path segment means no token. Returning "" would put an empty token in
    the registry and produce a request to the provider's root."""
    lines = [
        '{"url": "https://jobs.ashbyhq.com"}',
        '{"url": "https://jobs.ashbyhq.com/"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == []


def test_a_token_that_could_escape_a_url_is_dropped() -> None:
    """The token is interpolated into a provider URL later. Percent-encoded
    traversal survives urlsplit's path but must not survive this."""
    lines = [
        '{"url": "https://jobs.ashbyhq.com/%2E%2E%2Fadmin"}',
        '{"url": "https://jobs.ashbyhq.com/..%2F..%2Fetc"}',
        '{"url": "https://jobs.ashbyhq.com/good"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["good"]


def test_malformed_lines_are_skipped_not_fatal() -> None:
    """One bad row in a 400-row response must not lose the other 399."""
    lines = [
        "not json at all",
        '{"no_url_key": 1}',
        '{"url": 12345}',
        '{"url": "https://jobs.ashbyhq.com/survivor"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["survivor"]


def test_is_deterministic_and_sorted() -> None:
    """board-discovery.md §13: same input, same token set, twice.

    Sorted rather than insertion-ordered so the candidate file's diff stays
    reviewable — an unordered set would reshuffle the whole file on every run,
    and a diff nobody can read is how a review step becomes a rubber stamp.
    """
    first = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    second = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    assert first == second == sorted(first)


def test_lever_has_no_crawl_pattern() -> None:
    """ADR 0006, asserted rather than left as a comment.

    jobs.lever.co/robots.txt disallows CCBot, so Lever job pages are not in the
    archive and never will be. A pattern here would harvest zero tokens forever
    and read as a transient bug rather than a structural absence.
    """
    assert "lever" not in PROVIDER_PATTERNS


def test_greenhouse_queries_both_board_domains() -> None:
    """board-discovery.md §3: the newer domain contributed 433 tokens the older
    one did not, so querying only one loses a sixth of the index."""
    patterns = PROVIDER_PATTERNS["greenhouse"]
    assert any("boards.greenhouse.io" in p for p in patterns)
    assert any("job-boards.greenhouse.io" in p for p in patterns)


def test_takes_the_first_segment_rather_than_the_last() -> None:
    """Pins the rule directly, with a sub-path that is not a UUID.

    Written after a mutation showed the older job-id test could not tell a
    first-segment parser from a last-segment one: job ids are 36 characters and
    the length filter was rejecting them either way. A sub-path like `jobs` is
    short and well-formed, so only the segment rule itself can reject it.
    """
    lines = ['{"url": "https://jobs.ashbyhq.com/acme/jobs"}']
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["acme"]


def test_the_shape_rule_is_what_stops_a_traversal_not_the_decoding() -> None:
    """`_TOKEN_SHAPE` rejects `/` and `%`, so both spellings of a traversal die
    on the character set whether or not the segment was decoded first.

    Asserted because the comment in the module makes that claim, and a comment
    asserting a security property should have a test under it.
    """
    lines = [
        '{"url": "https://jobs.ashbyhq.com/%2E%2E%2Fadmin"}',
        '{"url": "https://jobs.ashbyhq.com/%2Fetc%2Fpasswd"}',
        '{"url": "https://jobs.ashbyhq.com/-leading-dash"}',
        '{"url": "https://jobs.ashbyhq.com/ok-token"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["ok-token"]
