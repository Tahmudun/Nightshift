"""The only module in the codebase that imports ``httpx``.

§7.3 lists what every adapter must do: identify itself, respect rate limits,
retry safely, avoid hammering endpoints, and be disableable. Implementing that
once here rather than per adapter is the difference between a policy and a
comment.

The kill switch is load-bearing rather than decorative. With
``OUTBOUND_HTTP_ENABLED=false`` — the default — this client refuses to open a
socket. That is what makes ``make demo`` offline by construction: an adapter
that quietly reached the network during a fixture test would be a mock becoming
the product (I7), in reverse.
"""

from __future__ import annotations

import asyncio
import random
from types import TracebackType
from typing import Any, Final, Self

import httpx
import structlog

from nightshift.adapters.base import SourceUnavailableError
from nightshift.config import Settings, get_settings

log = structlog.get_logger(__name__)

# Retry only what a retry can fix. A 404 means the board is gone and retrying it
# three times is just three times the rudeness.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: How much of an HTML body :meth:`PoliteClient.get_text` will read.
#:
#: A board page is HTML meant for a browser and can be megabytes of application
#: JavaScript; the only thing any caller wants from it is the ``<head>``. 256 KB
#: is far more than a head and it means a sweep over thousands of candidates has
#: a memory ceiling somebody chose rather than one it inherited from the widest
#: page on the internet.
MAX_TEXT_BYTES: Final = 256 * 1024


class OutboundHTTPDisabledError(SourceUnavailableError):
    """Raised when live HTTP is attempted while the kill switch is off."""


class RateLimiter:
    """Single-process request pacer.

    Enforces a minimum interval between requests rather than a token bucket:
    with one worker polling a handful of boards, a burst allowance buys nothing
    and steady spacing is easier to reason about from the far end's access log.
    """

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_for = self._next_allowed_at - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
                now = loop.time()
            self._next_allowed_at = now + self._min_interval


class PoliteClient:
    """Rate-limited, self-identifying, retrying HTTP client for source adapters."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._limiter = RateLimiter(self._settings.source_requests_per_second)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.http_timeout_seconds),
            headers={
                # §7.3: identify ourselves. A maintainer reading their logs can
                # tell who we are and how to reach us.
                "User-Agent": self._settings.http_user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(self, url: str) -> Any:
        """GET and parse JSON, or raise :class:`SourceUnavailableError`.

        Every failure path funnels into that one exception type because callers
        must treat them identically under I3: a timeout, a 503, and a truncated
        body are all "we learned nothing", never "the jobs are gone".
        """
        if not self._settings.outbound_http_enabled:
            raise OutboundHTTPDisabledError(
                "outbound HTTP is disabled (OUTBOUND_HTTP_ENABLED=false); "
                "ingestion must run from committed fixtures"
            )
        if self._client is None:
            raise RuntimeError("PoliteClient must be used as an async context manager")

        attempts = self._settings.http_max_retries + 1
        last_error: str = "no attempt made"
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                last_status = None
            else:
                last_status = response.status_code
                if response.is_success:
                    try:
                        return response.json()
                    except ValueError as exc:
                        # A 200 with a broken body is a source problem, and
                        # retrying it occasionally does help (partial transfer).
                        last_error = f"invalid JSON: {exc}"
                elif response.status_code in _RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status_code}"
                else:
                    # Terminal: 404, 403, 401. Fail now, do not hammer.
                    raise SourceUnavailableError(
                        f"GET {url} failed with HTTP {response.status_code}",
                        http_status=response.status_code,
                    )

            if attempt < attempts:
                delay = _backoff_delay(attempt, self._settings.http_backoff_base_seconds)
                log.warning(
                    "source_request_retry",
                    url=url,
                    attempt=attempt,
                    of=attempts,
                    error=last_error,
                    retry_in=round(delay, 2),
                )
                await asyncio.sleep(delay)

        raise SourceUnavailableError(
            f"GET {url} failed after {attempts} attempt(s): {last_error}",
            http_status=last_status,
        )

    async def get_text(self, url: str) -> str:
        """GET a page and return a bounded prefix of its body as text.

        Added at M1c because an employer's name is not in Ashby's API — it is in
        the board page's ``<title>``. Everything about politeness, retries, the
        kill switch and :class:`SourceUnavailableError` is shared with
        :meth:`get_json` on purpose: a second HTTP path would be a second place
        to forget the rate limiter, and nothing outside this module imports
        httpx.

        Two deliberate differences from :meth:`get_json`:

        * **The body is truncated at** :data:`MAX_TEXT_BYTES` **rather than
          refused.** A truncated ``<head>`` still yields a title, whereas
          raising would misclassify a real board as ``unreachable`` — the same
          "absence of data is not data" mistake I3 forbids one level down.
        * **A non-JSON content type is fine.** Reading HTML is the entire point.
        """
        if not self._settings.outbound_http_enabled:
            raise OutboundHTTPDisabledError(
                "outbound HTTP is disabled (OUTBOUND_HTTP_ENABLED=false); "
                "discovery must run from committed fixtures"
            )
        if self._client is None:
            raise RuntimeError("PoliteClient must be used as an async context manager")

        attempts = self._settings.http_max_retries + 1
        last_error: str = "no attempt made"
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            await self._limiter.acquire()
            try:
                async with self._client.stream(
                    "GET", url, headers={"Accept": "text/html,*/*"}
                ) as response:
                    last_status = response.status_code
                    if response.is_success:
                        return await _read_capped(response)
                    if response.status_code in _RETRYABLE_STATUS:
                        last_error = f"HTTP {response.status_code}"
                    else:
                        # Terminal: 404, 403, 401. Fail now, do not hammer.
                        raise SourceUnavailableError(
                            f"GET {url} failed with HTTP {response.status_code}",
                            http_status=response.status_code,
                        )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                last_status = None

            if attempt < attempts:
                delay = _backoff_delay(attempt, self._settings.http_backoff_base_seconds)
                log.warning(
                    "source_request_retry",
                    url=url,
                    attempt=attempt,
                    of=attempts,
                    error=last_error,
                    retry_in=round(delay, 2),
                )
                await asyncio.sleep(delay)

        raise SourceUnavailableError(
            f"GET {url} failed after {attempts} attempt(s): {last_error}",
            http_status=last_status,
        )


async def _read_capped(response: httpx.Response) -> str:
    """Read at most :data:`MAX_TEXT_BYTES` of a streaming response, then stop.

    Stops pulling chunks once the cap is reached rather than reading the whole
    body and slicing it — the point is not to hold a megabyte, so downloading
    one first would defeat the exercise.
    """
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk[: MAX_TEXT_BYTES - size])
        size += len(chunk)
        if size >= MAX_TEXT_BYTES:
            break
    # ``errors="replace"``: a cap can land mid-character, and a title is still
    # readable with one replacement glyph in the body somewhere.
    return b"".join(chunks).decode(response.charset_encoding or "utf-8", errors="replace")


def _backoff_delay(attempt: int, base_seconds: float) -> float:
    """Exponential backoff with full jitter, capped at eight base intervals.

    Jitter matters even with one worker: without it, several boards failing in
    the same pass retry in lockstep, which is the retry storm §7.3 warns about.
    """
    ceiling = base_seconds * min(2.0 ** (attempt - 1), 8.0)
    return random.uniform(0.0, ceiling)
