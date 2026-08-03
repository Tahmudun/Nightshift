"""Conditional requests in ``PoliteClient``. M1d, ADR 0007.

A ``304 Not Modified`` is the cheapest answer a provider can give us, and it is
neither a failure nor an empty body. Everything here exists to keep those three
things distinct, because collapsing them is how a source that is working
perfectly closes every job on every unchanged board.

These mock the *network* via ``respx``, never the client — the code under test
is the real retry loop, the real rate limiter and the real kill switch. Mocking
the thing under test is the anti-pattern CLAUDE.md §8 names explicitly.

Measured 2026-08-02: Greenhouse, Lever and Ashby all serve an ``ETag`` and all
three answer ``304`` when it is sent back. ADR 0007 had verified only Greenhouse.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from nightshift.adapters.base import SourceUnavailableError
from nightshift.adapters.http import (
    ConditionalResponse,
    OutboundHTTPDisabledError,
    PoliteClient,
)
from tests.conftest import make_settings

URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
ETAG = 'W/"96ced7ed899bb76f1b2f37c3507e1e87"'


class TestSendingTheEtag:
    @respx.mock
    async def test_sends_if_none_match_when_given_an_etag(self) -> None:
        route = respx.get(URL).mock(
            return_value=httpx.Response(200, json={"jobs": []}, headers={"ETag": ETAG})
        )
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            await client.get_json_conditional(URL, etag=ETAG)

        assert route.calls[0].request.headers["if-none-match"] == ETAG

    @respx.mock
    async def test_omits_if_none_match_when_there_is_no_etag(self) -> None:
        """A board polled for the first time has nothing to revalidate against."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            await client.get_json_conditional(URL, etag=None)

        assert "if-none-match" not in route.calls[0].request.headers


class TestNotModified:
    @respx.mock
    async def test_a_304_is_reported_as_data_not_raised_as_an_error(self) -> None:
        respx.get(URL).mock(return_value=httpx.Response(304))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)

        assert result.not_modified is True
        assert result.payload is None
        assert result.http_status == 304

    @respx.mock
    async def test_a_304_keeps_the_etag_we_sent(self) -> None:
        """A 304 response may carry no ETag header of its own, and the stored
        value is still the valid one — it is what earned the 304."""
        respx.get(URL).mock(return_value=httpx.Response(304))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)

        assert result.etag == ETAG

    @respx.mock
    async def test_a_304_is_never_retried(self) -> None:
        """It is a successful answer. Retrying it is three times the rudeness for
        no information, and 304 is not in the retryable set."""
        route = respx.get(URL).mock(return_value=httpx.Response(304))
        async with PoliteClient(
            make_settings(outbound_http_enabled=True, http_max_retries=3)
        ) as client:
            await client.get_json_conditional(URL, etag=ETAG)

        assert route.call_count == 1

    @respx.mock
    async def test_a_304_does_not_raise_source_unavailable(self) -> None:
        """The regression this guards: 304 is not in _RETRYABLE_STATUS, so a
        client that checks only `is_success` falls straight through to the
        terminal branch and turns the cheapest success into an outage."""
        respx.get(URL).mock(return_value=httpx.Response(304))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)  # must not raise

        assert result.not_modified is True


class TestModified:
    @respx.mock
    async def test_a_200_returns_the_payload_and_the_new_etag(self) -> None:
        respx.get(URL).mock(
            return_value=httpx.Response(
                200, json={"jobs": [{"id": 1}]}, headers={"ETag": 'W/"fresh"'}
            )
        )
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)

        assert result.not_modified is False
        assert result.payload == {"jobs": [{"id": 1}]}
        assert result.etag == 'W/"fresh"'
        assert result.http_status == 200

    @respx.mock
    async def test_a_200_without_an_etag_header_yields_none(self) -> None:
        """Then there is nothing to store, and the next poll is unconditional.
        Storing the stale one would mean revalidating against a body we no
        longer have."""
        respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)

        assert result.etag is None


class TestSharedPolicy:
    """The conditional path must inherit every guarantee `get_json` has.

    A second HTTP path is a second place to forget the rate limiter, the retry
    budget and the kill switch — which is why `get_json` delegates here rather
    than the two living side by side.
    """

    @respx.mock
    async def test_the_kill_switch_blocks_it(self) -> None:
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
        async with PoliteClient(make_settings(outbound_http_enabled=False)) as client:
            with pytest.raises(OutboundHTTPDisabledError):
                await client.get_json_conditional(URL, etag=ETAG)

        assert route.call_count == 0

    @respx.mock
    async def test_it_retries_transient_failures(self) -> None:
        route = respx.get(URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"jobs": []}, headers={"ETag": 'W/"fresh"'}),
            ]
        )
        async with PoliteClient(
            make_settings(outbound_http_enabled=True, http_max_retries=2)
        ) as client:
            result = await client.get_json_conditional(URL, etag=ETAG)

        assert route.call_count == 2
        assert result.etag == 'W/"fresh"'

    @respx.mock
    async def test_a_404_still_raises_without_retrying(self) -> None:
        route = respx.get(URL).mock(return_value=httpx.Response(404))
        async with PoliteClient(
            make_settings(outbound_http_enabled=True, http_max_retries=3)
        ) as client:
            with pytest.raises(SourceUnavailableError):
                await client.get_json_conditional(URL, etag=ETAG)

        assert route.call_count == 1

    @respx.mock
    async def test_the_retry_budget_is_exhausted_then_it_gives_up(self) -> None:
        route = respx.get(URL).mock(return_value=httpx.Response(503))
        async with PoliteClient(
            make_settings(outbound_http_enabled=True, http_max_retries=2)
        ) as client:
            with pytest.raises(SourceUnavailableError):
                await client.get_json_conditional(URL, etag=ETAG)

        assert route.call_count == 3  # 1 attempt + 2 retries

    @respx.mock
    async def test_an_unconditional_request_is_still_sent_when_the_etag_is_none(self) -> None:
        """`get_json` is this method with no ETag, so this is the path every
        existing caller now takes."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            result = await client.get_json_conditional(URL)

        assert route.call_count == 1
        assert result.not_modified is False


class TestGetJsonIsUnchanged:
    """Every existing caller keeps its exact contract.

    `get_json` now delegates, so these are not redundant with the tests above:
    they pin the wrapper's return type, which is a payload rather than a
    ConditionalResponse.
    """

    @respx.mock
    async def test_it_still_returns_the_payload_itself(self) -> None:
        respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": [1, 2]}))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            assert await client.get_json(URL) == {"jobs": [1, 2]}

    @respx.mock
    async def test_it_never_sends_a_conditional_header(self) -> None:
        """Unconditional by construction: with no ETag the server cannot answer
        304, so `payload` is always present for this caller and no existing
        code has to learn about not_modified."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            await client.get_json(URL)

        assert "if-none-match" not in route.calls[0].request.headers

    @respx.mock
    async def test_it_still_raises_on_an_unreachable_source(self) -> None:
        respx.get(URL).mock(return_value=httpx.Response(404))
        async with PoliteClient(make_settings(outbound_http_enabled=True)) as client:
            with pytest.raises(SourceUnavailableError):
                await client.get_json(URL)

    @respx.mock
    async def test_it_still_raises_on_a_broken_body(self) -> None:
        respx.get(URL).mock(return_value=httpx.Response(200, text="not json at all"))
        async with PoliteClient(
            make_settings(outbound_http_enabled=True, http_max_retries=0)
        ) as client:
            with pytest.raises(SourceUnavailableError):
                await client.get_json(URL)


class TestConditionalResponseShape:
    def test_it_is_frozen(self) -> None:
        """Passed between the adapter and the poll-state writer; a mutable one
        invites 'fix up the etag later', which is how a stale ETag outlives the
        payload it belongs to."""
        response = ConditionalResponse(
            not_modified=False, payload={"jobs": []}, etag=ETAG, http_status=200
        )
        with pytest.raises(Exception):  # noqa: B017 - pydantic raises ValidationError
            response.etag = "changed"  # type: ignore[misc]
