/**
 * How tall the buildings somebody is hiring in actually are.
 *
 * A `building` placement carries a coordinate and a BIN, and that is enough to
 * stand a role in the right place on the ground. It says nothing about how far
 * up the roof is — and a marker at the wrong altitude is either buried inside
 * the tower it belongs to or hanging in the sky above it, both of which read as
 * "this role is not really here".
 *
 * The height is already on this machine. `darkStyle.ts` extrudes every
 * footprint from the same `height_roof` the archive carries, so this reads that
 * attribute off the features the map has loaded rather than adding a source, a
 * request or a second copy of NYC's building table.
 *
 * **It is partial by nature and that is designed for, not worked around.**
 * `querySourceFeatures` answers from loaded tiles, so a building the camera has
 * never been near has no height yet. `buildingField.ts` substitutes
 * `DEFAULT_ROOF_METRES` for a miss, and the substitution changes how high a
 * marker hangs and never where it stands — so an absent height cannot move a
 * role off its building, only up or down it.
 */

/** NYC Open Data publishes `heightroof` in feet; the scene is metres. */
const FEET_TO_METRES = 0.3048;

/** What this reads off a tile feature. Anything else on it is ignored. */
interface BuildingFeature {
  readonly properties?: unknown;
}

/**
 * Roof heights in metres, by BIN, from whatever the map currently has loaded.
 *
 * A footprint with no measured roof is **left out** rather than recorded as
 * zero. `darkStyle.ts` gives an unmeasured building a 25 ft default body so it
 * has some mass, and the same substitution here would put a marker at street
 * level on a building that plainly has a roof — a wrong number that looks
 * measured, where an absent one falls through to a default that is documented
 * as a guess.
 */
export function readRoofHeights(features: readonly BuildingFeature[]): Map<string, number> {
  const heights = new Map<string, number>();

  for (const feature of features) {
    const properties = feature.properties;
    if (typeof properties !== 'object' || properties === null) continue;

    const record = properties as Record<string, unknown>;
    const bin = record.bin;
    // `bin` is a string in the tiles (`"1086193"`), as is `height_roof`
    // (`"339.64"`). Coerced rather than trusted, because a number here and a
    // string in `company_locations.building_id` would miss on every lookup and
    // look exactly like "no tile has loaded yet".
    if (typeof bin !== 'string' && typeof bin !== 'number') continue;
    const key = String(bin);
    if (key === '') continue;

    const feet = Number(record.height_roof);
    // `Number('')` is 0 and `Number(undefined)` is NaN; both mean "not
    // measured" and both must fall through to the field's default.
    if (!Number.isFinite(feet) || feet <= 0) continue;

    const metres = feet * FEET_TO_METRES;
    // Tallest wins. A footprint split across tile boundaries arrives more than
    // once, and taking the last one seen would make a building's height depend
    // on tile load order — the same marker at two altitudes on two page loads,
    // for a reason nothing on screen could explain.
    const existing = heights.get(key);
    if (existing === undefined || metres > existing) heights.set(key, metres);
  }

  return heights;
}
