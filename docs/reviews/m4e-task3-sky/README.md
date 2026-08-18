# M4e Task 3 — the sky

Screenshots taken with `apps/web/.look.mjs` on 2026-08-18 and judged by the
human against `docs/design/references/02-skyline-grid-plane-light-columns.jpg`,
which is the acceptance test ADR 0031 sets for every look task in this
milestone. **Approved on 2026-08-18.** Downsampled to 1440px wide; captured at
2880×1800.

| File | Pose | What it shows |
|---|---|---|
| `1-before.png` | opening pose | MapLibre's `sky` block: a flat magenta band with a hard edge where the far ground stops |
| `2-after-opening-pose.png` | opening pose | the custom layer — graded sky, and the far ground dissolving into the horizon instead of ending at it |
| `3-after-sun-over-the-hudson.png` | z13.2, pitch 78, bearing 288 | the sun, at azimuth 285° / elevation 0.7°, with its halo running along the horizon |
| `4-after-from-the-harbour.png` | z13.5, pitch 78, bearing 8 | the same sky over the downtown skyline, from the south |

`1-before.png` still has the interface panels over it; every "after" was taken
with `.look.mjs`'s `bare` flag, which hides them. That difference is the capture
tool gaining the flag between the two shots, not a change to the product.

The decision and the measurements are ADR 0032. The frame cost in those shots is
a **software rasteriser's** and is evidence about nothing — the real numbers came
from `apps/web/.measure.mjs` in a headed browser and are in the ADR.
