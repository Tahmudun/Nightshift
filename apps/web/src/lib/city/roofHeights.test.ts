import { describe, expect, it } from 'vitest';

import { readRoofHeights } from './roofHeights';

/** The shape `querySourceFeatures` hands back, narrowed to what is read. */
function feature(properties: Record<string, unknown>) {
  return { properties };
}

describe('readRoofHeights', () => {
  it('converts the archive feet into the metres the scene is written in', () => {
    // 620 8th Avenue: 742.13 ft of roof. The tiles carry feet because NYC Open
    // Data does; every altitude in the scene is metres. A conversion missed
    // here puts a marker three times too high and still inside Manhattan,
    // which is exactly the error nobody catches by looking.
    const heights = readRoofHeights([feature({ bin: '1087186', height_roof: '742.13' })]);

    expect(heights.get('1087186')).toBeCloseTo(226.2, 1);
  });

  it('reads a bin and a height that arrive as strings', () => {
    // Both are strings in the archive — `"1086193"`, `"339.64"` — and this cost
    // a debugging session once already (PROGRESS, M4e Task 1).
    const heights = readRoofHeights([feature({ bin: '1080672', height_roof: '60' })]);

    expect(heights.has('1080672')).toBe(true);
  });

  it('skips a footprint NYC never measured rather than reporting a zero roof', () => {
    // 732 structures in the archive have no `height_roof`. A zero here would be
    // a marker at street level on a building that has a roof — worse than the
    // documented default, because it looks measured.
    const heights = readRoofHeights([
      feature({ bin: '1000000', height_roof: '0' }),
      feature({ bin: '1000001' }),
      feature({ bin: '1000002', height_roof: '' }),
    ]);

    expect([...heights.keys()]).toEqual([]);
  });

  it('skips a feature with no bin at all, rather than keying one on undefined', () => {
    expect(readRoofHeights([feature({ height_roof: '400' })]).size).toBe(0);
  });

  it('keeps the taller of two records for one building', () => {
    // A footprint can be split across tiles and arrive twice. Taking the last
    // one seen would make the height depend on tile load order, so the same
    // building would sit at two different altitudes between two page loads.
    const heights = readRoofHeights([
      feature({ bin: '1087186', height_roof: '100' }),
      feature({ bin: '1087186', height_roof: '742.13' }),
      feature({ bin: '1087186', height_roof: '90' }),
    ]);

    expect(heights.get('1087186')).toBeCloseTo(226.2, 1);
  });
});
