/**
 * Where a role goes when somebody *has* said where it is.
 *
 * The counterpart to `unresolvedField.ts`, and the two are opposites in the one
 * way that matters. That field arranges roles that have no position: every
 * number in it is a layout decision and none of them is a claim about New York.
 * **Every number in this file is a claim about New York**, and it is only
 * allowed to exist because a named human wrote an address in
 * `data/company-locations.yaml`, dated it, and NYC GeoSearch resolved it to a
 * street and a building identifier (`city.md` §4.4).
 *
 * So the rule here is the inverse of that file's rule 1: **the ground position
 * is not ours to choose.** It comes from `placement.latitude` /
 * `placement.longitude` and passes through `sceneFromLngLat` unmodified. There
 * is no nudging apart of overlapping stacks, no jitter to make a crowd legible,
 * no snapping to a grid. A role that cannot be drawn where its office is does
 * not get drawn here at all.
 *
 * What *is* ours to choose is the vertical: how far above the roof a marker
 * hangs, how far apart two of them sit, and where a name plate goes. Those are
 * drawing decisions about a marker, not assertions about a place, and they are
 * the only numbers in this module that were picked rather than measured.
 *
 * Pure and deterministic on the same terms as the unresolved field: the same
 * signals in produce the same transforms out, in the same order, so the
 * instance buffer can be rebuilt on every poll and every treatment change
 * without the city moving under somebody who did nothing.
 */

import type { CitySignal } from '@/lib/schemas';

import { sceneFromLngLat } from './mercator';
import type { FieldPlacement } from './unresolvedField';

/**
 * How high a roof is assumed to be before any tile has said.
 *
 * The building archive loads per tile, so a hiring building outside the
 * viewport has no measured `height_roof` yet and something has to be assumed
 * for one frame or a thousand. **This is the one number in this file that is a
 * guess, and it is a guess about a marker rather than about a place** — the
 * position underneath it is exact either way, and the moment a tile reports the
 * real roof the stack settles onto it.
 *
 * 250 m is chosen high rather than average on purpose. Too low and a beacon is
 * drawn *inside* the tower it belongs to, which reads as a rendering fault and
 * hides the role completely; too high and it briefly resembles the untethered
 * field, which is merely wrong-looking. Of the two failures only one is silent.
 */
export const DEFAULT_ROOF_METRES = 250;

/**
 * Metres between the roof and the lowest marker standing on it.
 *
 * Wide enough that the beam (ADR 0023) has a visible length before the first
 * beacon interrupts it, and that a marker is never confused with the lit crown
 * of the building itself, which `darkStyle.ts` draws in the top seven metres.
 */
export const ROOF_CLEARANCE = 60;

/**
 * Vertical gap between two roles at the same building.
 *
 * Deliberately the same 45 m as `ROLE_SPACING` in the unresolved field, and
 * deliberately a *separate constant*: the two stacks answer to different
 * pressures — this one competes with real skyline for room and that one does
 * not — so they are free to diverge without one silently dragging the other.
 */
export const ROOF_ROLE_SPACING = 45;

/**
 * Metres between the topmost role and the building's name plate.
 *
 * Same reasoning as `LABEL_GAP`: a plate sitting on the top beacon reads as a
 * caption for that one role instead of a heading for the building.
 */
export const ROOF_LABEL_GAP = 95;

/**
 * How far the beam carries on past the topmost role before it is gone.
 *
 * ADR 0023 asks for a column of light that *dissipates* into the sky rather
 * than one that stops. Ending it exactly at the last beacon would draw a hard
 * cap on the light, which reads as a solid object — a pillar rather than a
 * beam — and would put an edge where the design wants an absence.
 */
export const BEAM_OVERSHOOT = 140;

/**
 * One building with somebody hiring in it.
 *
 * Keyed by BIN — the New York City Building Identification Number that
 * GeoSearch returns and that the footprint archive carries on every feature —
 * because the BIN is what lets the renderer light *this* footprint rather than
 * approximate one at a coordinate.
 */
export interface HiringBuilding {
  /** The BIN. A string, as it is in the tiles: `"1087186"`. */
  readonly buildingId: string;
  /**
   * What to write on the plate.
   *
   * The employer's name when one employer is hiring here, and a count when
   * several are. **Not the first name found**, which is the version that puts
   * "Datadog" over the New York Times Building and thereby asserts an address
   * for a company that never claimed one.
   */
  readonly name: string;
  /**
   * Every role standing here, bottom to top, in the order the buffer draws
   * them. Ids rather than a count, for the reason `FieldColumn` gives: a panel
   * that re-derived this order would be a second implementation of the sort.
   */
  readonly jobIds: readonly string[];
  /** East of the anchor, in metres. Derived from the office's coordinate. */
  readonly x: number;
  /** North of the anchor, in metres. Derived from the office's coordinate. */
  readonly y: number;
  /**
   * Where the roof is, in metres above the ground plane.
   *
   * The beam starts here, because ADR 0023's hiring building is "a narrow
   * column of light leaving the roof" — a beam started at ground level would be
   * drawn straight through the tower it is supposed to be coming out of.
   */
  readonly roofAltitude: number;
  /** Where this building's plate goes: clear of the topmost marker. */
  readonly labelAltitude: number;
  /**
   * How far the beam rises above the roof, in metres.
   *
   * Sized to clear the whole stack rather than fixed, because the stack's
   * height is the number of roles open here. A beam that stopped short would
   * leave the top roles hanging over the light they are meant to be standing
   * in — which is exactly how the untethered field reads, and the two states
   * must never be able to look the same.
   */
  readonly beamHeight: number;
}

export interface BuildingField {
  readonly placements: readonly FieldPlacement[];
  /** Buildings in the order they are laid out, for plates and for navigation. */
  readonly buildings: readonly HiringBuilding[];
}

/** One building mid-grouping: what landed on it, before any of it is ordered. */
interface Cluster {
  readonly buildingId: string;
  readonly lng: number;
  readonly lat: number;
  readonly roles: CitySignal[];
  /** Employer ids, to tell "two roles at one company" from "two companies". */
  readonly companyIds: Set<string>;
  /** The single employer's name, kept only while there is exactly one. */
  firstCompanyName: string;
}

/**
 * Arrange every placed signal onto the building its employer confirmed.
 *
 * Signals that are not `building` placements are ignored rather than filtered
 * by the caller — the mirror of `arrangeUnresolved`, and for the same reason:
 * each field owns the rule about what belongs in it, so a corpus split between
 * them draws every role exactly once. A role drawn in both would appear twice
 * on the city, which reads as two openings.
 *
 * `roofHeights` maps BIN to a measured roof height in metres, as read from the
 * building tiles the map has actually loaded. It is optional and partial by
 * nature; a BIN it does not carry gets `DEFAULT_ROOF_METRES`. It changes only
 * how high a marker hangs, never where it stands.
 */
export function arrangeOnBuildings(
  signals: readonly CitySignal[],
  anchor: readonly [number, number],
  roofHeights?: ReadonlyMap<string, number>,
): BuildingField {
  const clusters = new Map<string, Cluster>();

  for (const signal of signals) {
    const { placement } = signal;
    if (placement.kind !== 'building') continue;
    // Belt and braces over `placementSchema`, which already refuses a `building`
    // without coordinates or a BIN. This is the last point before a number
    // becomes a position on a map, and I1 is worth two checks: without it a
    // schema loosened in a later milestone puts a role at the anchor, which is
    // a real address in Times Square.
    if (placement.latitude === null || placement.longitude === null) continue;
    if (placement.building_id === null) continue;

    const existing = clusters.get(placement.building_id);
    if (existing) {
      existing.roles.push(signal);
      existing.companyIds.add(signal.company_id);
    } else {
      clusters.set(placement.building_id, {
        buildingId: placement.building_id,
        lng: placement.longitude,
        lat: placement.latitude,
        roles: [signal],
        companyIds: new Set([signal.company_id]),
        firstCompanyName: signal.company_name,
      });
    }
  }

  const placements: FieldPlacement[] = [];
  const buildings: HiringBuilding[] = [];

  // Name, then BIN. The BIN breaks ties so two buildings whose plates read the
  // same still get a stable order rather than one that depends on which fetch
  // returned first — the same guarantee `arrangeUnresolved` gets from its
  // name-then-id pair.
  const ordered = [...clusters.values()].sort(
    (a, b) => nameOf(a).localeCompare(nameOf(b)) || a.buildingId.localeCompare(b.buildingId),
  );

  for (const cluster of ordered) {
    const { x, y } = sceneFromLngLat(anchor, cluster.lng, cluster.lat);
    const roofAltitude = roofHeights?.get(cluster.buildingId) ?? DEFAULT_ROOF_METRES;

    // Title, then job id. Alphabetical rather than by recency, because a stack
    // that reshuffles when a poll runs is a stack nobody can learn the shape
    // of — `unresolvedField`'s note on `sort` argues this at length and the
    // argument does not change when the roles are standing on something.
    const roles = [...cluster.roles].sort(
      (a, b) => a.title.localeCompare(b.title) || a.job_id.localeCompare(b.job_id),
    );

    roles.forEach((signal, depth) => {
      placements.push({
        jobId: signal.job_id,
        x,
        y,
        altitude: roofAltitude + ROOF_CLEARANCE + depth * ROOF_ROLE_SPACING,
      });
    });

    buildings.push({
      buildingId: cluster.buildingId,
      name: nameOf(cluster),
      jobIds: roles.map((role) => role.job_id),
      x,
      y,
      roofAltitude,
      labelAltitude:
        roofAltitude + ROOF_CLEARANCE + (roles.length - 1) * ROOF_ROLE_SPACING + ROOF_LABEL_GAP,
      beamHeight: ROOF_CLEARANCE + (roles.length - 1) * ROOF_ROLE_SPACING + BEAM_OVERSHOOT,
    });
  }

  return { placements, buildings };
}

/**
 * What a building's plate says.
 *
 * Counted by `company_id` rather than by name, because normalization keeps two
 * employers apart that a display name would merge — and merging them here would
 * print one company's name over the other company's roles.
 */
function nameOf(cluster: Cluster): string {
  return cluster.companyIds.size === 1
    ? cluster.firstCompanyName
    : `${cluster.companyIds.size} employers`;
}
