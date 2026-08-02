"""Board discovery: filling the registry with a pipeline instead of by hand.

Deliberately separate from ingestion. Ingestion never imports this package and
this package writes to no table ingestion reads; the only thing they share is
`data/board-registry.yaml`, and only a human ever puts anything into that.

Discovery is explicitly invoked and never scheduled (AMENDMENTS A1, ADR 0006).
It is a `make` target, not an ARQ cron.
"""
