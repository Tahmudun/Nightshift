"""Community internship lists, as job sources.

Two public files, each one HTTP request, each returning hundreds of employers
(the-hunt.md §5.2):

    https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json
    https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json

**The shape, and why it needs no pipeline change.** Every other adapter here
maps one board to one employer, and takes the employer's name from the registry
row a human approved. A list inverts that: one token, many employers, and the
employer's name is *in the payload*. `ingestion.py` already calls
`get_or_create_company` per job from `NormalizedSourceJob.company_name`, so a
multi-employer board needs nothing downstream to change — dedupe, `job_locations`,
freshness and scoring all work unchanged.

Field shapes were read off both real files on 2026-08-29 rather than from
documentation:

* The response is a **JSON array**. An object shape is a source problem, never
  evidence of zero jobs (I3).
* `company_name`, `title`, `locations`, `url`, `id`, `active`, `is_visible`,
  `sponsorship`, `date_posted` and `date_updated` appear in both files.
* **The two files disagree about their own schema.** Simplify carries `terms`
  (`["Summer 2026"]`) and `category`; vanshb03 carries `season` (`"Winter"`)
  and neither of the others. Nothing here reads any of the three — the season a
  posting is for is M3's classifier's question, off the title, and reading a
  field only one list publishes would make this adapter quietly worse on the
  other one.
* `date_posted` is epoch **seconds**, unlike Lever's milliseconds. Reading one
  as the other puts the date tens of thousands of years out, and every
  freshness calculation downstream inherits it.
* **There is no description.** An entry is a pointer to a posting, not the
  posting. `description_text` and `description_html` stay `None` and the score
  built on one says so, rather than this adapter inventing prose out of a title.
* `locations` is an array of strings and Simplify abbreviates: its home city is
  the bare token **`NYC`**, which carries 195 of its 206 New York roles, and
  `SF` appears 92 times. `NYC` resolves through the shared normalizer; `SF`
  does not, and lands `unknown` rather than being guessed at (I1).
* `active: false` is a **volunteer's belief about a board we do not poll**. It
  is preserved on the raw payload and it is not a closure signal — see I3 and
  `fetch_board` below.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import structlog

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    ListedPosting,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from nightshift.adapters.greenhouse import content_hash, normalize_title
from nightshift.adapters.http import ConditionalJsonClient
from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import infer_remote_policy, parse_location_list

log = structlog.get_logger(__name__)

#: Bumped when normalization changes, so a stored ETag earned by the old parser
#: is discarded rather than letting the new parser never see the payload it was
#: written for (ADR 0007).
PARSER_VERSION: Final = "1"

#: The two lists this adapter is instantiated for, by registry `ats` value.
#: Kept here rather than in the registry YAML because a raw URL is a piece of
#: code — the parser is written against that exact file — and a registry row is
#: data a person edits.
LIST_URLS: Final[dict[str, str]] = {
    "simplify_list": (
        "https://raw.githubusercontent.com/SimplifyJobs/"
        "Summer2027-Internships/dev/.github/scripts/listings.json"
    ),
    "vansh_list": (
        "https://raw.githubusercontent.com/vanshb03/"
        "Summer2027-Internships/dev/.github/scripts/listings.json"
    ),
}


def _epoch_seconds_to_datetime(value: object) -> datetime | None:
    """Convert the lists' second-resolution epoch to an aware UTC datetime.

    Returns None for anything unparseable, including a bool — `isinstance(True,
    int)` is True in Python, and `True` is not a timestamp.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _location_strings(payload: dict[str, Any]) -> list[str]:
    """Every location string the entry names, in the order the list gave them.

    Not re-ordered and not de-duplicated: A2 lets order carry meaning for
    sorting and nothing else, and the first entry is what `parse_location_list`
    marks primary.
    """
    locations = payload.get("locations")
    if not isinstance(locations, list):
        return []
    return [item.strip() for item in locations if isinstance(item, str) and item.strip()]


class InternshipListAdapter:
    """Implements :class:`~nightshift.adapters.base.JobSourceAdapter`.

    One instance per list. `list_name` is the registry's `ats` value, which is
    what makes two lists two sources rather than one — they overlap heavily, and
    collapsing them would make the dedupe layer's job invisible instead of doing
    it.
    """

    source_type = SourceType.INTERNSHIP_LIST
    parser_version = PARSER_VERSION
    #: The file carries every entry in full. There is no second request that
    #: could add anything, because there is nothing more to fetch — an entry
    #: has no description to go and get.
    is_two_phase = False

    def __init__(
        self,
        client: ConditionalJsonClient | None,
        *,
        list_name: str,
        raw_url: str,
    ) -> None:
        self._client = client
        self.source_name = list_name
        self._raw_url = raw_url

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        """Fetch the whole list. Never raises for a source failure.

        I3 lives or dies on this method: an unreachable host, a non-2xx, or a
        payload of the wrong shape becomes ``ok=False``, never an exception,
        because a caller that has to catch one is one refactor away from
        treating "the source errored" as "the list is empty" and closing every
        job that came from it.

        The bare ``except Exception`` is deliberate and is not defensive
        clutter. ``SourceUnavailableError`` is what the client *promises*; an
        ``httpx`` error escaping that promise is a bug somewhere else, and I3
        fixes the cost of that bug at one skipped list rather than at a closed
        board. It is logged at `error` so it cannot pass silently.

        **`active: false` is not read here and closes nothing.** A volunteer
        marking an entry inactive is a belief about a board this project does
        not poll; the entry is returned like any other and the flag rides along
        on the untouched payload, where a later question can still ask it.
        """
        if self._client is None:
            raise RuntimeError("InternshipListAdapter needs a client to fetch")
        try:
            response = await self._client.get_json_conditional(self._raw_url, etag=etag)
        except SourceUnavailableError as exc:
            log.warning(
                "internship_list_unavailable",
                list_name=self.source_name,
                board=board.token,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))
        # Deliberately broad. See the docstring: I3 over tidiness.
        except Exception as exc:
            log.error(
                "internship_list_unexpected_error",
                list_name=self.source_name,
                board=board.token,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return FetchOutcome(board=board, ok=False, error=str(exc))

        if response.not_modified:
            # Zero writes downstream. The file is byte-identical to the copy we
            # already parsed, which matters more here than on any ATS board:
            # Simplify's file is 11 MB.
            return FetchOutcome(board=board, ok=True, not_modified=True, etag=etag, http_status=304)

        payload = response.payload
        if not isinstance(payload, list):
            # A 200 with the wrong shape is a source problem, and "no jobs" is
            # the one conclusion we must not draw from it.
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=response.http_status,
                error=(
                    f"unexpected payload shape: expected a JSON array, got {type(payload).__name__}"
                ),
            )

        jobs: list[RawJob] = []
        for entry in payload:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            if not isinstance(entry.get("company_name"), str) or not entry["company_name"].strip():
                # The employer name is the whole shape of this source. An entry
                # without one cannot become a company row, and guessing from the
                # URL slug is the I2 failure ADR 0005 exists to catch.
                continue
            if not isinstance(entry.get("title"), str) or not entry["title"].strip():
                continue
            jobs.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=str(entry["company_name"]).strip(),
                    canonical_url=entry.get("url") or None,
                    payload=entry,
                )
            )

        log.info(
            "internship_list_fetched",
            list_name=self.source_name,
            board=board.token,
            entries=len(payload),
            jobs=len(jobs),
        )
        return FetchOutcome(
            board=board,
            ok=True,
            jobs=tuple(jobs),
            listed=tuple(
                ListedPosting(
                    source_job_id=job.source_job_id,
                    # Both lists publish `date_updated`, but it moves whenever a
                    # volunteer edits the row rather than when the employer
                    # changes the posting. Feeding it to conditional polling
                    # would re-fetch on somebody's typo fix.
                    source_updated_at=None,
                )
                for job in jobs
            ),
            etag=response.etag,
            http_status=response.http_status,
        )

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Map one entry, taking the employer name from the entry itself.

        This is the one adapter where `board.company` is *not* the employer.
        The list names the employer per row, which is the entire reason one
        request is worth hundreds of boards — and `board.company` here names
        the list ("Simplify Summer 2027"), not a company.
        """
        payload = raw_job.payload

        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError(f"{self.source_name} entry {raw_job.source_job_id} has no title")

        company_name = str(payload.get("company_name") or "").strip()
        if not company_name:
            raise ValueError(f"{self.source_name} entry {raw_job.source_job_id} has no employer")

        locations = parse_location_list(_location_strings(payload))

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=company_name,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            # There is no description on a list entry. `content_hash(None)`
            # gives every entry from a list the same hash, which is correct and
            # load-bearing: change detection for this source is the rest of the
            # normalized row, and a hash invented from the title would report a
            # change every time a volunteer retitled something.
            description_html=None,
            description_text=None,
            description_hash=content_hash(None),
            # The one fact the list states about every entry by being what it
            # is. Not inferred from the title — that is M3's classifier's job.
            employment_type=EmploymentType.INTERNSHIP,
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            # A10: a list entry carries no salary and no deadline. None means
            # "not provided by source", and the UI says exactly that.
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            salary_period=None,
            application_deadline=None,
            source_published_at=_epoch_seconds_to_datetime(payload.get("date_posted")),
            # `date_updated` moves when a volunteer edits the row, not when the
            # employer changes the posting. Recording it as a source's
            # modification stamp would be a claim the file does not make.
            source_updated_at=None,
        )
