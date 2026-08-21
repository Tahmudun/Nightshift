"""The MCP server: Nightshift's domain, exposed to the user's own Claude.

ADR 0038, milestone M5c. AMENDMENTS A16 is why this exists and why it is the
rung the rest of the product hangs from:

    Four separate-looking asks — reading LinkedIn/Indeed, "link the app to
    Claude", AI rejection analysis, and a voice assistant — are **one MCP
    server** exposing this domain to Claude. Built once, the other three are
    configuration and UI.

It is also why the AI in this product is free. **Nightshift never calls a
model.** The user's own Claude is the model; this package supplies
deterministic evidence and Claude narrates it.

Two rules govern everything in here.

**This package reaches Nightshift over HTTP and never through the database.**
It may import `httpx`. It may not import `nightshift.db.session`,
`nightshift.db.models`, or SQLAlchemy — `tests/test_mcp_boundaries.py` fails if
it does. M5b made data isolation structural by attaching `require_session` once,
in `main.py`, so that a route is protected because it exists; a second door into
the domain would reintroduce exactly that hole. `nightshift.db.base` is the one
allowed import, because it holds enums and no engine: `shapes.py` reads
`LocationConfidence` so the confidence table can be proven exhaustive over it.

**A tool description is not documentation — it is the last place an invariant
can be enforced.** Every earlier milestone could hold I1 and I4 in a constraint,
a type or a test. This one cannot: if a result carries
`location_confidence: "city_only"` and the description does not say what that
licenses a reader to claim, Claude will write "this role is at 620 8th Avenue"
— fluently, and falsely. The schema stops a coordinate arriving bare; only the
description stops it being *read* as a street address.
"""
