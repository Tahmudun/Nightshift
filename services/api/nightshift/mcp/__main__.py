"""The stdio entry point. `python -m nightshift.mcp`.

This is the process Claude Desktop launches, and the only module here that
knows what a transport is.

**Everything it writes to stdout is protocol.** On stdio the transport *is*
stdout: one stray `print`, one logging handler left on the default stream, and
the JSON-RPC framing is corrupt. The symptom is Claude Desktop reporting that
the server failed, with nothing useful in any log a person thinks to open. So
:func:`_log_to_stderr` runs before anything else, and
`tests/test_mcp_boundaries.py` drives this module through a real pipe and
asserts every line of stdout parses as a JSON-RPC frame.

Configuration is two environment variables, set in `claude_desktop_config.json`
by `nightshift tokens --create`. Both are required and a missing one is fatal:
starting anyway would show as connected in Claude Desktop and fail at the first
tool call, with an authentication error that gives no hint the config file is
the problem.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from nightshift.mcp.client import NightshiftClient
from nightshift.mcp.server import build_server

#: Read from the environment Claude Desktop passes in. These names are printed
#: by `nightshift tokens --create` and asserted in `test_tokens_command.py`, so
#: a rename here breaks a test rather than a person's config file silently.
ENV_API_URL = "NIGHTSHIFT_API_URL"
ENV_TOKEN = "NIGHTSHIFT_MCP_TOKEN"

DEFAULT_API_URL = "http://localhost:8000"


def _log_to_stderr() -> None:
    """Pin every handler to stderr, and do it before anything can log.

    `basicConfig` alone is not enough — it is a no-op if the root logger
    already has a handler, which any earlier import may have added. So the root
    is reconfigured with ``force=True``, and `nightshift.logging`'s
    `configure_logging` is deliberately **not** called: it is written for a
    server and a CLI, both of which own their stdout.
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("NIGHTSHIFT_MCP_LOG_LEVEL", "WARNING").upper(),
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(  # noqa: T201 - stderr, and the only thing a person will see
            f"error: {name} is not set.\n"
            f"  Mint a token and get the config block to paste with:\n"
            f"    nightshift tokens --email <you> --create --label 'claude desktop'",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return value


async def _serve() -> None:
    token = _require(ENV_TOKEN)
    api_url = os.environ.get(ENV_API_URL, "").strip() or DEFAULT_API_URL

    # The client is closed when the transport ends, which is when Claude
    # Desktop closes the pipe. There is one connection for the process's whole
    # life, which is what a long-lived subprocess wants.
    async with NightshiftClient(api_url, token) as client:
        await build_server(client).run_stdio_async()


def main() -> None:
    _log_to_stderr()
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:  # pragma: no cover - a person pressing ^C
        pass


if __name__ == "__main__":
    main()
