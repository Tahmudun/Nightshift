"""Invariant I5, asserted structurally rather than promised in a docstring.

There is no code path in this project that submits an application. The claim is
worth a test because it is the kind of thing that stays true until one
convenient afternoon.

Two independent assertions:

1. The one HTTP client this system has is read-only. `PoliteClient` exposes no
   method that writes to a source, and `test_http_client.py`'s sibling rule —
   nothing outside `adapters/http.py` imports httpx — means there is no second
   client to check.
2. No route handler in the API is named for submitting.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from nightshift.adapters.http import PoliteClient
from nightshift.api.main import create_app


def test_the_only_http_client_can_only_read() -> None:
    public = {
        name
        for name, _ in inspect.getmembers(PoliteClient, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public == {"get_json", "get_json_conditional", "get_text"}, (
        "PoliteClient grew a method. If it writes to a source, invariant I5 is "
        "gone; if it reads, add it here deliberately."
    )


def test_no_route_handler_submits_anything() -> None:
    app = create_app()
    names = {getattr(route, "name", "") for route in app.routes}
    offenders = {name for name in names if any(verb in name for verb in ("submit", "autoapply"))}
    assert offenders == set()


def test_the_stage_machine_is_the_only_thing_that_moves_a_stage() -> None:
    """`change_stage` is the single writer of `current_stage`.

    Anything else assigning that attribute is a stage change with no event
    behind it, which is a history with a hole in it.
    """
    root = Path(__file__).resolve().parents[1] / "nightshift"
    # Compared by full path, not by basename. There are two `applications.py`
    # in this tree — the domain module and the route module — and excluding by
    # name would let a route assign the column directly and stay invisible.
    machine = root / "domain" / "applications.py"
    # `=` but not `==`. A plain substring search matches
    # `Application.current_stage == stage`, which is a filter, not a write.
    assignment = re.compile(r"\.current_stage\s*=(?!=)")
    offenders = [
        path
        for path in root.rglob("*.py")
        if assignment.search(path.read_text()) and path != machine
    ]
    assert offenders == [], f"these assign current_stage outside the machine: {offenders}"
