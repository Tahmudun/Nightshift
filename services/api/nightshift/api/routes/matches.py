"""The ranked list: one person's corpus, banded by eligibility, best first.

`matching.md` §5.3. Its own router rather than another query parameter on
`/jobs`, and the reason is what the two resources are. `/jobs` is the corpus —
the same rows for everybody, ordered by recency, and PRODUCT-SPEC §24's ranking
is deliberately absent from it. This is a list of `match_results`, which exist
only for a person, and every row here is a claim about them.

Folding the two together would mean one endpoint whose response shape, ordering
and meaning all change with a flag, and whose filters would then have to be
answered twice — once against jobs the sweep has scored and once against jobs it
has not. Splitting them makes `not_yet_scored` a number this route can state
plainly instead of a discrepancy the caller has to notice.

Routes validate and delegate: the banding is `domain/matching.BAND_ORDER`, the
ordering is one SQL clause in `domain/matching.ranked_for`, and this file groups
what comes back.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import CurrentUserId
from nightshift.api.routes.jobs import to_match, to_summary
from nightshift.api.schemas import (
    DeferredComponentOut,
    MatchRankingOut,
    RankedBandOut,
    RankedJobOut,
)
from nightshift.db.session import get_db_session
from nightshift.domain.matching import BAND_ORDER, ranked_for
from nightshift.domain.scoring import DEFERRED_COMPONENTS

router = APIRouter(prefix="/matches", tags=["matches"])

MAX_LIMIT = 200


@router.get("", response_model=MatchRankingOut)
async def list_matches(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 100,
) -> MatchRankingOut:
    """Every scored open posting for the current user, grouped and ranked.

    No pagination beyond `limit`, deliberately. An offset into a banded list is a
    position inside a structure the client did not build, and the first honest
    version of "page 2 of the eligible band" is a per-band cursor — which is worth
    building when the corpus is large enough to need one. It is 31 postings.
    """
    ranking = await ranked_for(session, user_id=user_id, limit=limit)

    grouped: dict[str, list[RankedJobOut]] = {state.value: [] for state in BAND_ORDER}
    for job, result in ranking.rows:
        match = to_match(result)
        # `to_match` returns `None` only for a `None` row, and `ranked_for`
        # selected on the current version — so this is unreachable rather than
        # handled. Asserted instead of silently skipped: a row dropped here is a
        # posting missing from a ranked list with the count above it still right.
        assert match is not None
        grouped[result.eligibility_status.value].append(
            RankedJobOut(job=to_summary(job), match=match)
        )

    return MatchRankingOut(
        # Every band, empty or not. A section that vanishes when nobody is in it
        # makes `ineligible` invisible exactly when there is nothing in it to see,
        # and §3.3's promise that such a posting is shown and dimmed rather than
        # hidden is only checkable if the heading is there to be empty.
        bands=[
            RankedBandOut(
                state=state,
                items=grouped[state.value],
                unassessed=sum(1 for row in grouped[state.value] if row.match.fraction is None),
            )
            for state in BAND_ORDER
        ],
        total=len(ranking.rows),
        not_yet_scored=ranking.not_yet_scored,
        ruleset_version=ranking.ruleset,
        deferred_components=[
            DeferredComponentOut(
                name=deferred.name,
                weight=deferred.weight,
                blocked_on=deferred.blocked_on,
                reason=deferred.reason,
            )
            for deferred in DEFERRED_COMPONENTS
        ],
    )
