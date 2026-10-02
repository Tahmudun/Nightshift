"""Which cities Nightshift is about. ADR 0041, answering Q14.

The first live pass filled the corpus with what the boards publish, and three
quarters of it is not New York: 384 roles are remote or address-unknown, and
521 are physically somewhere else (San Francisco, London, Toronto...). Q14 was
answered on 2026-10-02: **filter to New York now, without making New York the
limit** — the other major tech cities are next.

So a *market* is a named set of cities, and ``MARKETS`` (the setting) says which
are enabled. Today that is ``nyc``. Turning on San Francisco later is
``MARKETS=nyc,sf-bay-area``: the definitions below already exist, nothing is
stored per market, and nothing needs re-polling or backfilling, because the
scope is evaluated when a job is read, from locations ingestion already keeps.

**What the scope hides, and what it never hides.** A job is out of scope only on
positive knowledge: every location it names is a known city, and none of those
cities is in an enabled market. A remote role is in scope. So is any role with
a location the parser could not resolve, and a role with no location at all:
"we could not tell where this is" is not evidence that it is elsewhere, the
same temperament as I3. Nothing is deleted. ``source_job_records`` and canonical
jobs keep everything the boards publish (Q14's caveat), the operational views
show everything, and every read path that applies the scope reports what it
excluded rather than letting it disappear.

**Matching** is on the parsed city name, casefolded, the way polling tiers have
always asked "is this NYC". A state or country the parser found must agree with
the market; one it did not find does not disqualify. That is what keeps
Cambridge, Massachusetts apart from Cambridge, United Kingdom, and London from
London, Ontario. ``MARKETS=all`` turns the scope off entirely. Recognising a
city name is not knowing where a building is (I1); this decides which roles are
shown, never where a point is drawn.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, exists, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm.util import AliasedClass

from nightshift.db.base import JobStatus, LocationConfidence
from nightshift.db.models import Job, JobLocation
from nightshift.domain.locations import NYC_CITY_NAMES


@dataclass(frozen=True, slots=True)
class Market:
    """One metro: the city names it covers, and the state/country they belong to.

    ``cities`` are casefolded. ``states`` and ``countries`` are spelled the way
    :mod:`nightshift.domain.locations` writes them ("California", "USA",
    "United Kingdom"). A location's state or country, when the parser found
    one, must be among them. So London's empty ``states`` means any state
    disqualifies: London, Ontario is not London.
    """

    key: str
    name: str
    cities: frozenset[str]
    states: frozenset[str] = frozenset()
    countries: frozenset[str] = frozenset()

    def contains(self, city: str | None, state: str | None, country: str | None) -> bool:
        if city is None or city.casefold() not in self.cities:
            return False
        if state is not None and state not in self.states:
            return False
        return country is None or country in self.countries


def _market(
    key: str, name: str, cities: Iterable[str], *, states: Iterable[str], country: str
) -> Market:
    return Market(
        key=key,
        name=name,
        cities=frozenset(c.casefold() for c in cities),
        states=frozenset(states),
        countries=frozenset({country}),
    )


#: Every market Nightshift can be scoped to. Defined here, enabled by the
#: ``MARKETS`` setting. Adding a metro is an entry here and a test; enabling one
#: is configuration.
#:
#: ``nyc`` is ``NYC_CITY_NAMES`` exactly, the codebase's single definition of
#: "is this NYC" (polling tiers and discovery ask it too). Jersey City and
#: Hoboken are therefore not in it; widening it means widening that definition,
#: deliberately, in one place.
MARKETS: dict[str, Market] = {
    market.key: market
    for market in (
        Market(
            key="nyc",
            name="New York City",
            cities=NYC_CITY_NAMES,
            states=frozenset({"New York"}),
            countries=frozenset({"USA"}),
        ),
        _market(
            "sf-bay-area",
            "San Francisco Bay Area",
            [
                "San Francisco",
                "South San Francisco",
                "Oakland",
                "Berkeley",
                "Emeryville",
                "San Mateo",
                "Redwood City",
                "Menlo Park",
                "Palo Alto",
                "Mountain View",
                "Sunnyvale",
                "Santa Clara",
                "Cupertino",
                "San Jose",
                "Fremont",
            ],
            states={"California"},
            country="USA",
        ),
        _market(
            "seattle",
            "Seattle",
            ["Seattle", "Bellevue", "Redmond", "Kirkland"],
            states={"Washington"},
            country="USA",
        ),
        _market(
            "boston",
            "Boston",
            ["Boston", "Cambridge", "Somerville"],
            states={"Massachusetts"},
            country="USA",
        ),
        _market("austin", "Austin", ["Austin"], states={"Texas"}, country="USA"),
        _market(
            "los-angeles",
            "Los Angeles",
            ["Los Angeles", "Santa Monica", "Culver City", "Playa Vista", "Venice"],
            states={"California"},
            country="USA",
        ),
        _market("chicago", "Chicago", ["Chicago"], states={"Illinois"}, country="USA"),
        _market(
            "washington-dc",
            "Washington, DC",
            ["Washington", "Arlington", "Alexandria", "Bethesda"],
            states={"District of Columbia", "Virginia", "Maryland"},
            country="USA",
        ),
        _market("london", "London", ["London"], states=(), country="United Kingdom"),
        _market("toronto", "Toronto", ["Toronto"], states={"Ontario"}, country="Canada"),
    )
}


#: ``MARKETS=all`` turns the scope off: everything ingested is shown, as it was
#: before ADR 0041. The answer to "New York should not be the limit" that does
#: not wait for a market to be defined.
EVERYWHERE = "all"


@dataclass(frozen=True, slots=True)
class Scope:
    """What the product shows: some markets, or everywhere."""

    markets: tuple[Market, ...]
    everywhere: bool = False

    @property
    def names(self) -> list[str]:
        return ["Everywhere"] if self.everywhere else [m.name for m in self.markets]


def parse_market_keys(raw: str) -> tuple[str, ...]:
    """``"nyc, sf-bay-area"`` -> ``("nyc", "sf-bay-area")``. Raises on an unknown key.

    An unknown key fails loudly: a typo in ``MARKETS`` silently scoping the
    whole product to nothing would look exactly like an empty market. ``all``
    stands alone; "all and also nyc" means nothing.
    """
    keys = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not keys:
        raise ValueError("MARKETS names no market; it must name at least one (e.g. MARKETS=nyc)")
    if EVERYWHERE in keys:
        if len(keys) > 1:
            raise ValueError(f"MARKETS={EVERYWHERE} turns the scope off and cannot be combined")
        return keys
    unknown = [key for key in keys if key not in MARKETS]
    if unknown:
        raise ValueError(
            f"MARKETS names unknown market(s) {unknown}; known: "
            f"{', '.join(sorted(MARKETS))}, or {EVERYWHERE}"
        )
    return keys


def scope_of(keys: Sequence[str]) -> Scope:
    if tuple(keys) == (EVERYWHERE,):
        return Scope(markets=(), everywhere=True)
    return Scope(markets=tuple(MARKETS[key] for key in keys))


def current_scope() -> Scope:
    """The ``MARKETS`` setting, as a scope."""
    from nightshift.config import get_settings

    return scope_of(get_settings().enabled_markets)


#: The scope of the city view, whatever ``MARKETS`` says. The city *is* New
#: York — its basemap, its buildings, its offices — so it shows New York's roles
#: and the placeless ones (the Island), and nothing else, even with San
#: Francisco enabled or the scope off. Otherwise `placement`'s third rule (a
#: role inherits its employer's confirmed office) would draw a Denver role on
#: its employer's Manhattan building, which is Q14's 521 on screen.
NEW_YORK = Scope(markets=(MARKETS["nyc"],))


def market_of(city: str | None, state: str | None, country: str | None) -> Market | None:
    """The defined market a parsed location falls in, enabled or not."""
    return next((m for m in MARKETS.values() if m.contains(city, state, country)), None)


# ---------------------------------------------------------------------------
# The rule, in SQL. `in_scope_filter` is what read paths apply; the location
# predicates are the same rule as `Market.contains`, and a test holds the two
# to the same answers.
# ---------------------------------------------------------------------------


#: A `job_locations` row: the mapped class itself, or an alias of it.
type _Locations = type[JobLocation] | AliasedClass[JobLocation]


def _location_in(market: Market, loc: _Locations) -> ColumnElement[bool]:
    # `x IN ()` is false, so an empty `states` leaves only "the parser found no
    # state", which is `Market.contains`' rule exactly.
    return and_(
        func.lower(loc.city).in_(sorted(market.cities)),
        or_(loc.state.is_(None), loc.state.in_(sorted(market.states))),
        or_(loc.country.is_(None), loc.country.in_(sorted(market.countries))),
    )


def location_in_markets(
    markets: Sequence[Market], loc: _Locations = JobLocation
) -> ColumnElement[bool]:
    """A ``job_locations`` row in one of ``markets``."""
    return or_(*(_location_in(m, loc) for m in markets)) if markets else false()


def location_is_placeless(loc: _Locations = JobLocation) -> ColumnElement[bool]:
    """A row that names no known city: remote, or not resolved. Never out of scope."""
    return or_(loc.city.is_(None), loc.location_confidence == LocationConfidence.REMOTE)


def in_scope_filter(scope: Scope | None = None) -> ColumnElement[bool]:
    """Jobs the scope keeps: any location in one of its markets, any placeless one, or none."""
    scope = current_scope() if scope is None else scope
    if scope.everywhere:
        return true()
    # Aliased, so the filter composes inside a query that already selects from
    # `job_locations` (the coverage report does): unaliased, the subquery would
    # correlate to the outer row and ask about one location instead of the job.
    loc = aliased(JobLocation)
    located = select(loc.id).where(loc.job_id == Job.id)
    return or_(
        ~exists(located),
        exists(
            located.where(or_(location_is_placeless(loc), location_in_markets(scope.markets, loc)))
        ),
    )


def out_of_scope_filter(scope: Scope | None = None) -> ColumnElement[bool]:
    """Jobs every one of whose locations is a known city outside the scope's markets."""
    scope = current_scope() if scope is None else scope
    return false() if scope.everywhere else ~in_scope_filter(scope)


# ---------------------------------------------------------------------------
# What the scope leaves out, for the coverage page.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ElsewhereCount:
    """Open roles outside the enabled markets that name this place.

    ``market_key`` is set when the place belongs to a defined market that is not
    enabled, so the page can say "turn on sf-bay-area"; it is None for a city no
    market covers yet.
    """

    label: str
    market_key: str | None
    jobs: int


@dataclass(frozen=True, slots=True)
class MarketScopeReport:
    scope: Scope
    open_in_scope: int
    open_out_of_scope: int
    #: Largest first. A role naming two outside cities counts under both, so
    #: these can sum to more than `open_out_of_scope`.
    elsewhere: tuple[ElsewhereCount, ...]


async def market_scope_report(
    session: AsyncSession, scope: Scope | None = None, *, top: int = 12
) -> MarketScopeReport:
    """Open jobs in and out of the scope, and where the others are."""
    scope = current_scope() if scope is None else scope
    is_open = Job.status == JobStatus.OPEN

    async def count(*where: ColumnElement[bool]) -> int:
        return int(
            (
                await session.execute(select(func.count()).select_from(Job).where(*where))
            ).scalar_one()
        )

    open_in = await count(is_open, in_scope_filter(scope))
    open_out = await count(is_open, out_of_scope_filter(scope))

    rows = (
        await session.execute(
            select(JobLocation.job_id, JobLocation.city, JobLocation.state, JobLocation.country)
            .join(Job, Job.id == JobLocation.job_id)
            .where(is_open, out_of_scope_filter(scope), JobLocation.city.is_not(None))
        )
    ).all()
    places: dict[tuple[str, str | None], set[object]] = {}
    for job_id, city, state, country in rows:
        market = market_of(city, state, country)
        key = (market.name, market.key) if market else (_place_label(city, state, country), None)
        places.setdefault(key, set()).add(job_id)
    elsewhere = sorted(
        (
            ElsewhereCount(label=label, market_key=key, jobs=len(ids))
            for (label, key), ids in places.items()
        ),
        key=lambda e: (-e.jobs, e.label),
    )
    return MarketScopeReport(
        scope=scope,
        open_in_scope=open_in,
        open_out_of_scope=open_out,
        elsewhere=tuple(elsewhere[:top]),
    )


def _place_label(city: str | None, state: str | None, country: str | None) -> str:
    return ", ".join(part for part in (city, state or country) if part)
