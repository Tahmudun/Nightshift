"""The tools, their descriptions, and nothing that knows a transport.

ADR 0038. `build_server` takes a client and hands back an :class:`MCPServer`
with the tools bound to it. Nothing in this module mentions stdio — that is
`__main__.py`'s single job — so adding Streamable HTTP at M7, when there is
somewhere to deploy to, is a second entry point rather than a rewrite.

**Read the descriptions as code.** They are the last place invariants I1 and I4
can be enforced, because the consumer is a language model rather than a
renderer: a result can be correct and its reading false. That is the failure
class new to this milestone.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from nightshift.mcp.client import NightshiftClient

#: What the model is told about this server before it calls anything.
#:
#: The two paragraphs do different jobs. The first says what Nightshift is, so
#: tool selection is sensible. The second is I1 and I5 stated once at the top,
#: because a rule repeated per result is a rule a long conversation drifts away
#: from — the per-result `means` fields restate it where it is read, and this
#: establishes it where the conversation starts.
INSTRUCTIONS = """\
Nightshift is a live database of New York technology job listings, plus the \
reader's own profile, saved jobs and application pipeline. It ingests postings \
from company job boards, deduplicates them, and scores them against a profile \
the reader has confirmed.

Two rules govern how you may talk about anything this server returns.

**Never state where a job is more precisely than its location tells you.** \
Every location carries a `confidence` and a plain-English `means` field. \
Repeat what `means` says; do not upgrade it. A role whose confidence is \
`city_only` is in New York and its street address is unknown — saying \
otherwise invents a fact about a real company.

**Never take an irreversible action on the reader's behalf.** You can search, \
read, explain and capture. You cannot confirm a captured posting, change an \
application's stage, or apply to anything — those are the reader's to do, in \
Nightshift itself. Capturing a posting creates a *proposal* the reader reviews; \
it is not a decision, and you should say so when you make one.\
"""


def build_server(client: NightshiftClient, *, name: str = "nightshift") -> MCPServer:
    """Assemble the server around ``client``.

    A factory rather than a module-level singleton because the client is the
    thing that varies: the entry point builds one against a real URL, and the
    tests build one against an in-process ASGI transport. A module-level server
    would force the tests to reach in and swap a global, which is how a test
    ends up asserting against the swap rather than the code.
    """
    mcp: MCPServer = MCPServer(name=name, instructions=INSTRUCTIONS)

    @mcp.tool(
        name="whoami",
        description=(
            "Return the Nightshift account this connection is authenticated as. "
            "Use it to confirm the link is working, or when the reader asks which "
            "account Claude is connected to. Takes no arguments."
        ),
    )
    async def whoami() -> dict[str, Any]:
        """The signed-in account.

        Deliberately the first tool built and deliberately trivial: it proves
        the whole path — config, transport, client, bearer token, `/auth/me`,
        `require_session` — before any domain surface rides on it. When the
        link is broken this is the tool that says so in one call.
        """
        return await client.get("/auth/me")

    return mcp
