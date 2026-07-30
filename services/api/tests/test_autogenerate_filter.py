"""What the CI drift probe is allowed to see.

`make migrate` up/down/up proves migrations are reversible. The drift probe
proves the models and the migrations still agree. This filter decides which
tables that comparison covers, so it can fail in two directions and only one of
them is loud:

- too narrow, and CI reports drift that is not ours — noisy, but it stops the
  build and someone looks at it;
- too broad, and drift detection quietly stops working for whatever it hides.

The second is why the "never exclude a table in the models" case below exists.
"""

from __future__ import annotations

from nightshift.db import models  # noqa: F401 - registers the models on Base.metadata
from nightshift.db.autogenerate import POSTGIS_BOOKKEEPING, build_include_object
from nightshift.db.base import Base

# Real tables the CI image's postgis_tiger_geocoder and postgis_topology bring
# with them. These exact names appeared as "Detected removed table" in the first
# CI run that got far enough to reach the drift probe.
TIGER_TABLES = frozenset(
    {"addrfeat", "faces", "featnames", "county_lookup", "loader_platform", "pagc_lex"}
)
TOPOLOGY_TABLES = frozenset({"topology", "layer"})
EXTENSION_OWNED = TIGER_TABLES | TOPOLOGY_TABLES


class _FakeIndex:
    def __init__(self, table_name: str) -> None:
        self.table = type("_T", (), {"name": table_name})()


class TestExcludesWhatIsNotOurs:
    def test_extension_tables_are_excluded(self) -> None:
        include = build_include_object(Base.metadata, EXTENSION_OWNED)
        for name in sorted(EXTENSION_OWNED):
            assert include(None, name, "table", True, None) is False, name

    def test_postgis_bookkeeping_is_excluded_without_a_connection(self) -> None:
        """Offline mode passes an empty set; the static names must still hold."""
        include = build_include_object(Base.metadata, frozenset())
        for name in sorted(POSTGIS_BOOKKEEPING):
            assert include(None, name, "table", True, None) is False, name

    def test_indexes_on_extension_tables_are_excluded(self) -> None:
        include = build_include_object(Base.metadata, EXTENSION_OWNED)
        idx = _FakeIndex("addrfeat")
        assert include(idx, "idx_addrfeat_geom_gist", "index", True, None) is False


class TestIncludesWhatIsOurs:
    def test_every_project_table_is_compared(self) -> None:
        include = build_include_object(Base.metadata, EXTENSION_OWNED)
        assert Base.metadata.tables, "no models registered — this test would pass vacuously"
        for name in Base.metadata.tables:
            assert include(None, name, "table", True, None) is True, name

    def test_indexes_on_project_tables_are_compared(self) -> None:
        include = build_include_object(Base.metadata, EXTENSION_OWNED)
        idx = _FakeIndex("job_locations")
        assert include(idx, "ix_job_locations_geom", "index", True, None) is True

    def test_an_unknown_table_is_still_compared(self) -> None:
        """A table nobody claims is drift, not noise — it must not be filtered."""
        include = build_include_object(Base.metadata, EXTENSION_OWNED)
        assert include(None, "some_table_someone_added_by_hand", "table", True, None) is True


class TestTheFilterCannotHideRealDrift:
    def test_a_model_table_wins_over_extension_ownership(self) -> None:
        """The guard that stops the filter disabling itself.

        If an extension ever ships a table named like one of ours, believing
        pg_depend would switch off drift detection for that table — silently,
        and for the one table we most need it on.
        """
        ours = next(iter(Base.metadata.tables))
        include = build_include_object(Base.metadata, EXTENSION_OWNED | {ours})
        assert include(None, ours, "table", True, None) is True

    def test_a_model_table_wins_for_indexes_too(self) -> None:
        include = build_include_object(Base.metadata, EXTENSION_OWNED | {"job_locations"})
        idx = _FakeIndex("job_locations")
        assert include(idx, "ix_job_locations_geom", "index", True, None) is True
