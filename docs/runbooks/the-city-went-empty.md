# The city went empty

**Symptom.** `/explore/city` says **"Nothing is on a building yet"** and the
readout reads `On a building: 0`, when you know addresses are in
`data/company-locations.yaml`.

**This looks exactly like a correct product state, and that is the problem.**
The empty-city screen is a real thing this product says, on purpose, and it was
written to be convincing. Nothing on screen distinguishes "no address has been
confirmed" from "the addresses were confirmed and the table was emptied".

## Check first

```
docker exec nightshift-postgres-1 psql -U nightshift -d nightshift \
  -c "select count(*) from company_locations;"
```

- **Zero rows, and the worksheet has addresses in it** → the table was emptied.
  Fix below.
- **Rows present** → this is not the runbook you want. The problem is between
  the database and the screen: check `GET /city/signals` and its `counts`.

## Fix

```
OUTBOUND_HTTP_ENABLED=true make offices
```

Idempotent — running it twice updates rather than duplicates — and it prints one
line per company, so you can see what came back.

**Check `geocode_cache` too.** If it was emptied as well, that run just made
real requests to `geosearch.planninglabs.nyc`, so it needed the network:

```
docker exec nightshift-postgres-1 psql -U nightshift -d nightshift \
  -c "select count(*) from geocode_cache;"
```

The cache is what ADR 0022's offline guarantee rests on: an address is geocoded
once, ever, and the buildings it placed survive into an offline `make demo`. A
refilled cache restores that. An empty one means the next person to run
`make offices` needs the network again.

## Why it happens

**`make check` does this.** The Python suite runs against the same Postgres the
dev stack uses, and the tests covering `company_locations` and `geocode_cache`
truncate them. So does anything else that runs `pytest` against a live stack.

This is the same shared-database fact that produces the other documented trap —
a `TRUNCATE` deadlock between a test and a live dev session, which shows up as
one pytest test hanging and then failing on its own. Same cause, different
symptom.

**`make seed` and `make reset-db` do not restore this.** The offices are not
seed data; they come from a file a human wrote and a live geocoder resolved, so
nothing in the seed path can rebuild them.

## The real fix, which is not done

A separate test database, so the suite cannot touch the dev stack at all. It is
`docs/QUESTIONS.md` Q8 and it needs a decision because it changes `make test`,
CI, and `conftest.py` — it is a workflow migration rather than a patch.

Until then: **run `make offices` after `make check`** if you care about the city
having buildings on it.
