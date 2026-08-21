"""The authenticated HTTP client. The only module here that knows a URL.

ADR 0038 §1. Every rule this product has — I5's two-step, capture scoping,
`require_session`'s default-deny — lives at the HTTP boundary, and this is how
the MCP server goes through it like any other client.

The two things worth reading before changing anything in this file are
:class:`NightshiftUnavailableError` and why ``http`` is injectable.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx


class NightshiftUnavailableError(RuntimeError):
    """Nightshift could not be reached or could not answer. **Never an empty result.**

    This class exists for invariant I3, arriving on a new surface. I3 says a
    source returning an error, a timeout or an empty array is not evidence a
    job closed — and the MCP server meets the same problem one level up.

    Claude Desktop launches this server whether or not `make dev` is running.
    If `search_jobs` answered an unreachable API with ``[]``, Claude would say
    *"there are no backend internships open in New York"* — which is fluent,
    confident, and a lie produced by a connection refused on port 8000. The
    person would have no way to tell that from a real empty result.

    So an outage **raises**, the message names the cause and the fix, and MCP
    turns a raised exception into a visible tool error rather than an answer.
    """


class NightshiftClient:
    """An `httpx` client that carries a session token and nothing clever.

    ``http`` is injectable, and that is the seam this whole milestone is tested
    through: the tests hand it an ``ASGITransport`` pointed at the real FastAPI
    app, so a tool call runs against real routes, real `require_session` and
    real auth — with no network and no port. A mocked client would test the
    mock (`CLAUDE.md` §8), and a live port would make the suite depend on
    something started by hand.

    The token goes in ``Authorization: Bearer``, which `api/deps.py` has
    accepted since M5b and whose docstring names this server as the reason.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {token}"}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the transport, but only if this object opened it.

        A client handed in by a caller — a test, or a future entry point that
        shares one — belongs to that caller. Closing it here would work exactly
        once and then fail in a way that reads as a protocol bug.
        """
        if self._owns_client:
            await self._http.aclose()

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        return await self._request("GET", path, params=self._clean(params))

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    @staticmethod
    def _clean(params: dict[str, Any]) -> dict[str, Any]:
        """Drop ``None``s.

        A tool argument nobody supplied must not become ``?status=None`` in a
        query string, which the API would reject as an invalid enum member —
        an error about a filter the person never asked for.
        """
        return {key: value for key, value in params.items() if value is not None}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = await self._http.request(method, url, headers=self._headers, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise NightshiftUnavailableError(
                f"Nightshift's API is not reachable at {self._base_url}. "
                "Start it with `make dev` in the Nightshift repository, then try again. "
                "No conclusion should be drawn about the corpus from this failure."
            ) from exc
        except httpx.TimeoutException as exc:
            raise NightshiftUnavailableError(
                f"Nightshift's API at {self._base_url} did not answer in time. "
                "It may be starting up, or the query may be unusually large. "
                "This is not evidence that there are no results."
            ) from exc

        if response.status_code == httpx.codes.UNAUTHORIZED:
            # Named separately because the fix is completely different from
            # every other failure, and it is the one a person will actually
            # hit: a token that expired, or was revoked, or was pasted wrong.
            raise NightshiftUnavailableError(
                "Nightshift rejected this token. Mint a new one with "
                "`nightshift tokens --email <you> --create --label 'claude desktop'`, "
                "paste it into claude_desktop_config.json, and restart Claude Desktop."
            )

        if response.is_error:
            raise NightshiftUnavailableError(
                f"Nightshift answered {response.status_code} for {method} {path}: "
                f"{_detail(response)}"
            )

        payload: object = response.json()
        if not isinstance(payload, dict):
            # Every route this server calls returns an object. A list or a bare
            # scalar means the API changed shape underneath us, and failing here
            # is better than handing a tool something its type says it is not —
            # which is how a `KeyError` surfaces to a person as "Claude broke".
            raise NightshiftUnavailableError(
                f"Nightshift returned {type(payload).__name__} for {method} {path}, "
                "where an object was expected. The API and this server disagree about "
                "the shape of a response."
            )
        return payload


def _detail(response: httpx.Response) -> str:
    """FastAPI's ``detail``, or the raw body if this was not FastAPI answering.

    A proxy, a crash, or an HTML error page all end up here, and quoting a
    truncated body is more use to whoever is debugging than "an error occurred".
    """
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    return str(payload)[:200]
