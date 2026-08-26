# ADR 0040 — A gazetteer, decided at build time

- **Status:** accepted
- **Date:** 2026-08-25
- **Milestone:** M6a
- **Supersedes:** ADR 0008 on scope only. Every guardrail in 0008 survives.

## Context

`parse_location_segment` will not promote an uncorroborated bare token to a
city. That refusal is load-bearing: it is what keeps `Global`,
`Multiple Locations` and `Remote` out of the city column. ADR 0008 carved out
one exception — `_DECIDED_BARE_PLACES`, an enumerated reviewed list — and it
contains New York City, its five boroughs, and nothing else.

ADR 0008 named the cost and predicted this ADR:

> `"London"`, `"Toronto"`, `"Springfield"` and every other bare city name stay
> `unknown`. This is a real coverage gap and belongs on the coverage page under
> named blind spots.
>
> If a future milestone wants worldwide bare-city resolution, it needs a real
> gazetteer, a provenance field on the resolution, and its own ADR. Extending
> this list to get there would be the slow version of the thing this ADR
> refuses.

The gap is now measured rather than anticipated. In the 1200-job corpus,
**118 primary locations resolve to `unknown` with every field null while their
`raw_text` reads `London`, `San Francisco`, `Barcelona`, `Milton Keynes`.**
Seventeen distinct names, 128 rows in all.

M6 is the milestone that cannot proceed around it. `docs/architecture/archipelago.md`
§4 sorts every role onto a landmass by **how much is known about where the work
happens**. With the gap open, 70% of the furthest landmass — the one that
claims nothing is known — would be roles whose posting names a city outright.
Saying "we do not know where this is" about a job in London is a smaller lie
than inventing a street, and it is still the product telling the reader
something untrue.

## Decision

A committed gazetteer, built from GeoNames `cities15000` (CC BY 4.0, free,
offline, no key, no quota — A4), consulted only where ADR 0008's decided list
is consulted today: a bare uncorroborated token that survived every other
parsing rule.

**Every judgement is made at build time and committed.** What ships is
`data/city-gazetteer.tsv` — 14,293 name keys, each already marked `resolved`
with its display name or `ambiguous` with none. The parser performs a dictionary
lookup, not an evaluation. This is the point of the design, and it is what
preserves ADR 0008's first property ("it is enumerated and committed — a reader
can see the entire list") at a scale nobody would enumerate by hand. The list is
greppable, reviewable in a diff, and changes only when someone regenerates it
and a human reads the result.

Three rules produce it, each of them a refusal:

1. **Population floor, 50,000.** The long tail is where ordinary English words
   turn out to be towns: `Best` (29k), `Central` (28k), `Liberty` (30k),
   `University` (41k) are all real places, and a job location field is full of
   ordinary English words. The floor keeps Palo Alto, Mountain View, Cupertino
   and Redmond, which is the population that matters for this product.
2. **Dominance ratio, 10×.** A contested name resolves only if the largest
   bearer is ten times the runner-up. `London` (21×) resolves; `Barcelona`
   (2.1×), `Springfield` (1.1×) and `Cambridge` (1.1×) do not. 5× was tried and
   rejected: it admits `Birmingham` (UK 1.16M against Alabama 196k), which an
   American employer could plausibly mean either way. **The rule is refuse on
   ambiguity, never pick the biggest.**
3. **No coordinates, by construction.** The dump carries latitude and longitude;
   the generator reads them and throws them away. The shipped file contains
   names only, so it is structurally incapable of fabricating a position. I1 is
   enforced by the shape of the artifact rather than by anyone remembering.

**Provenance.** `resolution_method` gains `gazetteer`. Any row whose city came
from a lookup rather than from the posting's own structure says so, and every
one of them is findable in a single query — which is what makes the decision
reversible without a re-crawl.

**Never on a remote-marked segment.** The corpus contains
`Remote - Pacific Time`, and `Remote - Austin` is the same shape — a string US
employers write constantly. A trailing token after a remote marker names a
*scope* — an anchor city, a time zone, a hiring region — not a workplace, so the
gazetteer is not consulted there at all. Without the guard a fully remote role
would carry a city it does not have.

**Output is `city_only` and never higher**, exactly as ADR 0008 ruled. The
resolution yields a city *name* and nothing else: no state, no country. The
posting said `London`; recording "United Kingdom" beside it would be inferring
past what the source wrote, which is the habit this whole area exists to
prevent.

## Why this is not the guessing I1 forbids

ADR 0008's three tests, applied to a list 1,500 times longer:

1. **Enumerated and committed** — see above. The scale changed; the property
   did not. 345 refusals ship *alongside* the resolutions rather than being
   dropped, so what the gazetteer declined to decide is auditable too, and the
   coverage page counts it.
2. **Cannot manufacture precision** — `city_only`, null coordinates, no
   geocoding. Strengthened here: the artifact has no coordinates in it.
3. **Residual error bounded and named** — see below.

## Consequences

- **The bound on a wrong resolution.** If a bare `Dallas` meant the village in
  Georgia rather than the city in Texas, the product records city `Dallas` at
  `city_only` with no coordinate, and the role lands on the `elsewhere_city`
  landmass — which is where it belongs under either reading. **No misresolution
  between two same-named cities can move a role onto New York**, because the
  New York landmass is decided by name and both readings carry the same name.
  The blast radius is a label, not a position.
- **The residual risk, named plainly.** `Normal` (Illinois, 54k) and `Union`
  (New Jersey, 57k) clear both the floor and the ambiguity rule and are also
  ordinary words. A location field consisting of exactly one of them, outside a
  remote marker, would resolve to a city. No such row exists in the corpus
  today. If one ever appears, the fix is a stoplist in this artifact's
  generator, not a change to the parser — and it is deliberately not being
  written in advance for a problem that has not occurred.
- **`Barcelona` stays `unknown`,** and so do 344 other contested names. Nine
  rows in today's corpus. This is the rule working, not a gap to close later by
  lowering the ratio.
- **`Menlo Park` (35k) is below the floor** and stays `unknown` when written
  bare. `Menlo Park, CA` parses without the gazetteer and is unaffected.
- **Regeneration is a reviewed act.** The generator is deterministic — same dump
  in, byte-identical file out — and the artifact carries the source digest and
  both parameters in its header. A regenerated file that moves a name across the
  resolved/ambiguous line shows up in the diff.
- **Attribution is required** by CC BY 4.0 and is carried in the artifact header
  and on the coverage page.
- **ADR 0008's list is not deleted.** New York and its boroughs stay in
  `_DECIDED_BARE_PLACES`: they resolve *state* as well as city, which the
  gazetteer deliberately does not, and ADR 0007's hot-tier decision depends on
  it. The gazetteer is consulted only after the decided list declines.
