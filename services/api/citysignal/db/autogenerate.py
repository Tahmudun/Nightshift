"""Which database objects autogenerate is allowed to compare.

This lives here rather than in `migrations/env.py` because env.py runs
migrations as an import side effect and therefore cannot be imported by a test.
The rule it encodes is worth a test: it decides what the CI drift probe can see,
and a filter that is too broad silently switches drift detection off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import MetaData
    from sqlalchemy.engine import Connection

# CREATE EXTENSION postgis creates these three. They are extension-owned, so
# `EXTENSION_OWNED_TABLES` finds them on any live connection; the literal set is
# what offline mode falls back to, having no connection to ask.
POSTGIS_BOOKKEEPING = frozenset({"spatial_ref_sys", "geometry_columns", "geography_columns"})

EXTENSION_OWNED_TABLES = text("""
    SELECT c.relname
    FROM pg_class c
    JOIN pg_depend d
      ON d.objid = c.oid
     AND d.classid = 'pg_class'::regclass
     AND d.deptype = 'e'
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
""")


class IncludeObject(Protocol):
    def __call__(
        self, obj: object, name: str | None, type_: str, *args: Any, **kwargs: Any
    ) -> bool: ...


def reflect_extension_owned(connection: Connection) -> frozenset[str]:
    """Names of tables and views that belong to an installed extension."""
    return frozenset(connection.scalars(EXTENSION_OWNED_TABLES))


def build_include_object(metadata: MetaData, extension_owned: frozenset[str]) -> IncludeObject:
    """Restrict autogenerate to tables this project actually owns.

    An extension brings its own tables, and autogenerate cannot tell they are
    not ours: it compares every reflected table against the models and proposes
    dropping whatever is missing. `CREATE EXTENSION postgis` alone contributes
    spatial_ref_sys and two views. A server carrying postgis_tiger_geocoder and
    postgis_topology contributes about forty more, in schemas those extensions
    put on the search path — which is what CI's prebuilt image does, so the
    drift probe reported forty phantom drops against an unchanged schema.

    Ownership is read from `pg_depend`, so this follows whatever is installed
    rather than a hand-maintained list that goes stale.

    A name present in the models is never excluded, whatever pg_depend says.
    Otherwise an extension shipping a table named like one of ours would switch
    off drift detection for that table — the filter would hide exactly the
    change it exists to surface.
    """
    owned = extension_owned | POSTGIS_BOOKKEEPING

    def _is_ours(name: str | None) -> bool:
        return name is not None and name in metadata.tables

    def include_object(
        obj: object, name: str | None, type_: str, *args: Any, **kwargs: Any
    ) -> bool:
        if _is_ours(name):
            return True
        if type_ == "table":
            return name not in owned
        if type_ == "index":
            table_name = getattr(getattr(obj, "table", None), "name", None)
            if _is_ours(table_name):
                return True
            if table_name is not None:
                return table_name not in owned
        return True

    return include_object
