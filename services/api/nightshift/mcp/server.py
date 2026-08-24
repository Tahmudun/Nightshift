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

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from typing import Any

from mcp.server import MCPServer

from nightshift.mcp import shapes
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


#: Where a person reviews a capture. Not the API's URL — the two are different
#: services on different ports, and handing a reader `:8000/operate/capture`
#: sends them to a 404 at the end of the one flow this milestone is judged on.
DEFAULT_WEB_URL = "http://localhost:3000"


def _server_version() -> str:
    """The version Claude Desktop shows beside the connector's name.

    Read from installed package metadata rather than imported from
    `nightshift.api`: ADR 0038 forbids this package importing the API's
    internals, and `health.py`'s `VERSION` sits behind a module that opens a
    database session. Metadata is the one copy of the number both can agree on
    without a dependency.

    It was the empty string until 2026-08-21 — the SDK's default, never set.
    Caught by a probe that launched this server the way Claude Desktop does,
    minutes before the app was first pointed at it, so no reader ever saw it.
    That is luck rather than process: a connector showing no version reads as
    "this thing is broken" before a single tool is called.
    """
    try:
        return _package_version("nightshift")
    except PackageNotFoundError:  # pragma: no cover - only when run from a tree
        return "0+unknown"


def build_server(
    client: NightshiftClient,
    *,
    name: str = "nightshift",
    web_url: str = DEFAULT_WEB_URL,
) -> MCPServer:
    """Assemble the server around ``client``.

    A factory rather than a module-level singleton because the client is the
    thing that varies: the entry point builds one against a real URL, and the
    tests build one against an in-process ASGI transport. A module-level server
    would force the tests to reach in and swap a global, which is how a test
    ends up asserting against the swap rather than the code.
    """
    mcp: MCPServer = MCPServer(name=name, instructions=INSTRUCTIONS, version=_server_version())

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

    @mcp.tool(
        name="search_jobs",
        description=(
            "Search New York technology jobs in Nightshift's corpus. Returns "
            "matching postings with their locations, each carrying a confidence and "
            "a plain-English `means` field saying what that confidence licenses you "
            "to claim about where the role is.\n\n"
            "**Only open roles by default.** Nightshift tracks listings after they "
            "close, and a closed one presented as available wastes a reader's "
            "afternoon. Pass `status='closed'` to see those deliberately; every "
            "result states its own `status` either way.\n\n"
            "Results carry NO match score, deliberately. Call explain_match with a "
            "job id for a score and the evidence behind it, and never estimate one "
            "yourself.\n\n"
            "`q` searches job titles. Set `include_description` to widen it to the "
            "posting body. `skill` resolves through Nightshift's technology "
            "taxonomy, so 'GCP' finds postings stored as 'Google Cloud'. Filters "
            "left unset are not applied."
        ),
    )
    async def search_jobs(
        q: str | None = None,
        include_description: bool = False,
        company: str | None = None,
        skill: str | None = None,
        employment_type: str | None = None,
        remote_policy: str | None = None,
        status: str = "open",
        limit: int = 25,
    ) -> dict[str, Any]:
        """`GET /jobs`, reshaped so every location states its own confidence.

        **`status` defaults to `open` here and to nothing at the route**, which
        is the fix for a defect this milestone shipped and then found by
        reading rather than by running. `GET /jobs` filters on status only when
        given one, so passing none returns every status — while this tool's
        description promised open roles. A closed listing would have reached a
        reader as an available job.

        The seeded corpus is 32 jobs and all 32 are `open`, so the live walk
        could not have surfaced it; `test_mcp_read_tools.py` builds the closed
        job the corpus cannot supply.

        The default is a **default and not a filter**: `status="closed"` still
        works, and `get_job` on a known id always answers. I3 forbids
        presenting a closed role as open, not knowing about one.
        """
        payload = await client.get(
            "/jobs",
            q=q,
            include_description=include_description or None,
            company=company,
            skill=skill,
            employment_type=employment_type,
            remote_policy=remote_policy,
            status=status,
            limit=limit,
        )
        return shapes.search_result(payload)

    @mcp.tool(
        name="get_job",
        description=(
            "Read one job posting in full: its description, its locations with "
            "their confidences, the requirements Nightshift extracted, and which "
            "sources it was seen on.\n\n"
            "Use it after search_jobs when the reader asks about a specific role. "
            "The score is NOT here — call explain_match for that.\n\n"
            "This answers for a job at any status, including one that has closed. "
            "Check `status` before describing a role as available."
        ),
    )
    async def get_job(job_id: str) -> dict[str, Any]:
        """`GET /jobs/{id}`."""
        return shapes.job_detail(await client.get(f"/jobs/{job_id}"))

    @mcp.tool(
        name="explain_match",
        description=(
            "Why Nightshift scored a job the way it did for this reader. The ONLY "
            "tool that returns a score, and it never returns one alone: every "
            "response carries the six components with what each was worth and why, "
            "the penalties applied, the ruleset version that computed it, and the "
            "evidence rows behind every skill claim.\n\n"
            "Report the breakdown, not just the number. A component marked "
            "`assessable: false` means the posting did not say enough to ask the "
            "question — that is NOT the same as scoring zero, and reporting it as "
            "zero blames a candidate for an employer's terse writing.\n\n"
            "`eligibility_status` sits beside the score and is never inside it. A "
            "job can be a strong score and still `ineligible`; say both.\n\n"
            "If `match` comes back null, no score exists yet. Say that rather than "
            "estimating one."
        ),
    )
    async def explain_match(job_id: str) -> dict[str, Any]:
        """`GET /jobs/{id}`, keeping only the parts that explain a score."""
        return shapes.match_explanation(await client.get(f"/jobs/{job_id}"))

    @mcp.tool(
        name="list_applications",
        description=(
            "The reader's own application pipeline: which jobs they saved or "
            "applied to, what stage each is at, and when they last moved.\n\n"
            "Read-only. You cannot change a stage, archive an application, or "
            "apply to anything — those are the reader's to do in Nightshift "
            "itself. If they ask you to move something, say what you would move "
            "and let them do it.\n\n"
            "`stage` filters to one stage. Archived applications are excluded "
            "unless `archived` is true."
        ),
    )
    async def list_applications(
        stage: str | None = None,
        archived: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """`GET /applications`."""
        payload = await client.get(
            "/applications", stage=stage, archived=archived or None, limit=limit
        )
        return shapes.application_list(payload)

    @mcp.tool(
        name="capture_posting",
        description=(
            "Save a job posting the reader found somewhere Nightshift does not "
            "ingest — LinkedIn, Indeed, a newsletter, a friend's message. Put "
            "the posting text in `raw_text`, verbatim and as complete as you have "
            "it. Nightshift never loads the page itself, so `raw_text` is the only "
            "thing it will ever know about this posting.\n\n"
            "This creates a PROPOSAL, not a job. Nightshift reads a title, a "
            "company and a location out of the text and stores them as suggestions "
            "the reader must review and confirm in the Nightshift web interface. "
            "Nothing is added to the corpus, nothing is placed on the map, and no "
            "application is created until they do.\n\n"
            "Say that when you use it. Tell the reader what was parsed, tell them "
            "what the parser could not read (a null field means it declined to "
            "guess, which is deliberate), and give them the review URL. Do not "
            "describe the posting as saved, tracked or added — it is none of those "
            "until a person confirms it.\n\n"
            "**Read `already_in_nightshift` before you report any of that.** "
            "Nightshift polls thousands of company job boards first-hand, so most "
            "New York tech postings a reader finds elsewhere are already in the "
            "corpus — with a location Nightshift trusts, a match score, and the "
            "employer's own board as the source. If that list has anything in it, "
            "lead with it and give the reader the job id. An EMPTY list is not the "
            "same as no duplicates: read `read_this_first`, which says so when "
            "nothing could be read from the text to search with.\n\n"
            "**Pass `source_url` whenever you have the link.** It is optional to "
            "the schema and it is the only thing that lets the review queue tell "
            "the reader where a posting came from — a capture without it shows as "
            "'Origin not recorded', because Nightshift will not guess a website "
            "from the text. It is stored and shown so the reader can go back to "
            "the page, and it is **never fetched**: Nightshift does not load "
            "LinkedIn or Indeed, and a test fails if this path ever tries. If the "
            "reader gave you a URL, or the page you are reading has one, send it. "
            "Do not invent or reconstruct one — a wrong link is worse than "
            "none.\n\n"
            "**`title`, `company_name` and `location_text` are optional, and they "
            "are QUOTES rather than readings.** If you have seen the posting and "
            "know which string is the employer, copy it exactly as it appears in "
            "`raw_text` — character for character, apart from whitespace and "
            "capitalisation, which are forgiven. Do not tidy it up, do not "
            "abbreviate it, do not supply a fact you know from elsewhere. A value "
            "that is not present in the text is refused and comes back in "
            "`assistant_refused`; a refusal is not an error and the capture still "
            "succeeds. If a field is refused and you can quote it properly, say so "
            "to the reader rather than calling the tool again with the same "
            "value.\n\n"
            "Leave them out when you are inferring rather than reading. Nightshift "
            "has its own parser and a blank field costs the reader four seconds of "
            "typing; a confidently wrong employer costs them a role attributed to "
            "the wrong company.\n\n"
            "You cannot confirm it yourself. There is no tool for that, and its "
            "absence is deliberate: approving this tool call is not the same as "
            "reviewing a parsed job title, and that difference decides whether a "
            "role ends up attributed to the right company."
        ),
    )
    async def capture_posting(
        raw_text: str,
        source_url: str | None = None,
        title: str | None = None,
        company_name: str | None = None,
        location_text: str | None = None,
    ) -> dict[str, Any]:
        """`POST /capture`. Creates a `pending` row and never confirms it.

        The three quote arguments are flat rather than one nested object
        because a schema a model fills in by hand is easier to get right one
        string at a time. They are reassembled into `assistant` here, which is
        the shape the route validates.
        """
        assistant = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
        }
        payload = await client.post(
            "/capture",
            json={
                "raw_text": raw_text,
                "source_url": source_url,
                "assistant": assistant if any(assistant.values()) else None,
            },
        )
        return shapes.capture_proposal(payload, web_url=web_url)

    return mcp
