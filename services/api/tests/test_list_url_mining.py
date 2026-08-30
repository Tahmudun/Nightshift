"""Board tokens, mined out of the URLs the internship lists already carry.

the-hunt.md §5.3: a list entry is a pointer, and most of them point at a
Greenhouse, Ashby or Lever board this repository already knows how to read. So
the lists are also a discovery front-end — and a far better one than a Common
Crawl sweep, because every token comes from a company that demonstrably hires
interns.
"""

from __future__ import annotations

import pytest

from nightshift.discovery.sources.list_urls import tokens_from_listing_urls


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/example/jobs/123", ("greenhouse", "example")),
        ("https://job-boards.greenhouse.io/example/jobs/123", ("greenhouse", "example")),
        ("https://jobs.ashbyhq.com/example/abc-def", ("ashby", "example")),
        ("https://jobs.lever.co/example/uuid", ("lever", "example")),
    ],
)
def test_a_board_url_yields_its_ats_and_token(url: str, expected: tuple[str, str]) -> None:
    assert tokens_from_listing_urls([url]) == [expected]


def test_a_non_board_url_yields_nothing() -> None:
    assert tokens_from_listing_urls(["https://example.com/careers/123"]) == []


def test_a_lookalike_host_is_not_a_board() -> None:
    """`capture_origin` matched with `in` and read `linkedin.com.evil.example`
    as LinkedIn (M5d). Same mistake, same shape, do not repeat it."""
    assert tokens_from_listing_urls(["https://boards.greenhouse.io.evil.example/x/jobs/1"]) == []


def test_a_subdomain_of_a_board_host_is_not_a_board() -> None:
    """The other half of the same mistake, in the other direction."""
    assert tokens_from_listing_urls(["https://evil.boards.greenhouse.io/x/jobs/1"]) == []


def test_duplicates_collapse_and_order_is_stable() -> None:
    urls = [
        "https://jobs.ashbyhq.com/beta/1",
        "https://jobs.ashbyhq.com/alpha/2",
        "https://jobs.ashbyhq.com/beta/3",
    ]
    assert tokens_from_listing_urls(urls) == [("ashby", "beta"), ("ashby", "alpha")]


def test_a_url_with_no_path_yields_nothing() -> None:
    assert tokens_from_listing_urls(["https://jobs.ashbyhq.com/"]) == []


def test_a_token_that_could_not_be_polled_is_rejected() -> None:
    """The token is interpolated into a provider URL later. A segment that
    escapes the path is not a board, and must not become a candidate."""
    assert tokens_from_listing_urls(["https://jobs.ashbyhq.com/%2E%2E%2Fetc/x"]) == []
    assert tokens_from_listing_urls(["https://jobs.ashbyhq.com/a b/x"]) == []


def test_an_ashby_application_segment_is_not_a_token() -> None:
    """`application` appears after a token on Ashby apply URLs, never as one."""
    assert tokens_from_listing_urls(["https://jobs.ashbyhq.com/application"]) == []


def test_a_greenhouse_embed_url_is_read_from_its_query_string() -> None:
    """Greenhouse's embedded board puts the token in `?for=`, and the lists
    carry these. Reading only the path would silently drop them."""
    assert tokens_from_listing_urls(
        ["https://boards.greenhouse.io/embed/job_app?for=example&token=123"]
    ) == [("greenhouse", "example")]


def test_a_uuid_is_not_mistaken_for_a_token() -> None:
    """Lever and Ashby both put a job UUID in the path. Segment 1 is the board;
    a length rule keeps a 36-character UUID from becoming a registry row."""
    assert (
        tokens_from_listing_urls(["https://jobs.lever.co/3fd9615a-d0c7-458c-a0fc-5d9d7f0ce77c"])
        == []
    )


def test_case_in_the_host_does_not_change_the_answer() -> None:
    assert tokens_from_listing_urls(["https://Jobs.AshbyHQ.com/Example/x"]) == [
        ("ashby", "Example")
    ]


def test_a_url_that_is_not_a_url_is_skipped_rather_than_raising() -> None:
    """One malformed entry in 14,918 must not cost the other 14,917."""
    assert tokens_from_listing_urls(["", "not a url", "://", None]) == []  # type: ignore[list-item]
