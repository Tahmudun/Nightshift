# Visual references

Four images supplied by the human on 2026-08-11, before M4 began, as the intended
feel for the city.

> **This file used to say "they are reference, not target", and that sentence
> was wrong — ADR 0029, 2026-08-16.** The reasoning was that all four light
> every building while Nightshift lights only the ones with something to say, so
> the images could set a mood and never a goal. It was tidy and it cost two
> milestones. On 2026-08-13 `04-edge-outlined-towers-starfield.jpg` was handed
> back, byte-for-byte the same file, with the note that the vision had not been
> met. **These are the target.** What the old sentence was actually protecting —
> that a lit building must mean something — is protected now by hue, shape and a
> stated brightness margin instead: the scenery is neon and carries nothing, a
> hiring building is magenta, an open role is cyan and brighter than either.

What each one is here for is written in `docs/architecture/city.md` §2, which is
the document that turns them into rules. Summary:

| File | What it contributes |
|---|---|
| `01-street-canyon-vertical-bars.jpeg` | Light as **linear elements** — vertical bars and edge strips on dark masses — rather than as glowing surfaces. One warm column reading as focus against a cyan/magenta field. |
| `02-skyline-grid-plane-light-columns.jpg` | **Vertical beams rising out of buildings and fading into the sky.** This is the job beacon, already drawn. Also: the ground grid, and atmospheric haze behind the skyline for depth. |
| `03-ground-level-saturated-signage.jpg` | The **sky gradient**, and the idea that a surface on a building can carry content. The most stylised of the four and the least applicable — its saturation, palms and signage are scenery, and Nightshift is an instrument. |
| `04-edge-outlined-towers-starfield.jpg` | **Edge-outlined towers**: near-black mass, lit silhouette, sparse window speckle. The cheapest way to read a skyline as a skyline while keeping it dark. Also the starfield. |

Provenance: supplied from the human's own collection as mood reference. Nothing
here is copied into the product — no texture, no asset, no colour picked straight
off a pixel. The palette in `city.md` §3 is derived from the existing `ink*` /
`paper*` tokens and checked against WCAG, which these images would not pass.
