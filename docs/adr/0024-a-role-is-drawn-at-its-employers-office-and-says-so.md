# ADR 0024 — A role is drawn at its employer's office, and the drawing says so

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4c (Task 1)
- **Relates to:** `CLAUDE.md` I1; `city.md` §4.1, §4.4, §4.8, §6; ADR 0002; `nightshift/domain/office_loading.py`

## Context

`office_loading.py` ends with an explicit deferral:

> So the inheritance is a read-time join, and `ResolutionMethod.COMPANY_OFFICE`
> is what that join reports rather than something stored. **M4c builds it**,
> next to the renderer that needs it.

Building it surfaced a conflict between two documents this project treats as
binding, and the conflict is not cosmetic.

**`CLAUDE.md` I1, which outranks everything else in the repo:**

> Never fabricate a location. A job with location text `"New York, NY"` does not
> get placed on a building.

**`city.md` §4.4:**

> Jobs inherit their employer's building through their own `resolution_method` —
> never silently.

§4.1 measured that **every** posting in this corpus has location text of exactly
the kind I1 names: 0 of 247 name a street, across 139 distinct location strings,
10 location-bearing fields and three providers. So the two sentences are not
describing different cases that happen to overlap. They are describing the same
case, and they disagree about it. Read strictly, I1 means **no role in this
corpus may ever stand on a building**, and the skyline stays dark permanently no
matter how many addresses a human types.

## Decision

**A role is drawn at its employer's confirmed office, and every layer that
carries it also carries the fact that it was inherited.**

Concretely, in `nightshift/domain/placement.py`:

- A `Placement` carries `inherited: bool`, `office_label`, `office_address`, and
  `stated` — what the posting itself said, verbatim, kept beside the coordinate
  rather than replaced by it.
- `resolution_method` is `company_office` for an inherited placement, distinct
  from the rung that resolved the office itself.
- `location_confidence` describes **the coordinate**, not the claim that the
  role sits at it. Those are two different sentences and the schema keeps them
  in two different fields.
- Nothing is written back. `job_locations` still holds what the posting said,
  with `resolution_method = source_text_parse` and no coordinates.

## Why this is not a violation of I1

I1 prohibits **fabrication**: inventing a coordinate with no basis, or
presenting a guess as a measurement. Every clause of it is about a claim the
data cannot support — "never interpolate, never guess, never close enough."

An inherited placement is none of those. Its coordinate traces to a street
address a human wrote down and vouched for by name (`confirmed_by` and
`confirmed_at` are `NOT NULL` — ADR 0002's pattern, third instance), resolved by
a real geocoder to a real Building Identification Number. What is *inferred* is
the sentence "this role is at that office" — and that inference is labelled in
the data, in the API payload and in the interface, at every point where the
coordinate appears.

The reading that would forbid it also forbids the product. `city.md` §4.4 is not
a shortcut around I1; it is the answer to the question I1 raises, arrived at
after the census ruled out every other source of an address. Refusing the
inheritance would mean a city that can never light a building, which is not a
stricter reading of the invariant so much as an abandonment of the milestone.

**Where the line actually falls:** the placement is only as good as the office,
and the office cannot be better than `verified` without a street address —
`ck_company_locations_verified_requires_a_street_address` refuses it at the
database. So the chain from a lit building back to a human's signature is
unbroken and enforced below the code, which is the property that makes this
inference honest rather than convenient.

## The one rule here that is a product judgement

**A fully-remote role is not placed at its employer's office**, even when that
office is verified and every other role at the company is standing on it.

This does not follow from I1 — the coordinate would be true. It follows from
what the drawing *says*. A beacon on a building is a claim that the work happens
there, and for a remote role that claim is false while every number behind it is
correct. `remote` being its own `location_confidence` value is the spec already
saying so; this is that distinction reaching the renderer.

Hybrid roles **are** placed, because hybrid means partly there.

## Consequences

- The count of lit buildings is a count of confirmed facts, and it is bounded by
  how many addresses a human types (Q7). Today that number is zero and the
  honest render is every role in the unresolved layer — which `city.md` §4.8
  designs as the default view rather than the sad one.
- A detail panel showing an inherited placement **must** show the inheritance.
  A panel that renders the coordinate and drops `inherited` would report a fact
  the product does not have, and that is a bug in the panel rather than a
  looseness in this decision.
- A company correcting its office moves every role at once, with no stale rows
  left behind, because nothing was materialised.
- `Placement.__post_init__` refuses an impossible placement — an unresolved one
  with coordinates, a building below `verified`, an approximate point carrying a
  BIN — so the guarantee holds for callers this file has not met yet, not only
  for the cases its tests thought of.
