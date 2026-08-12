import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CityRoster } from './CityRoster';
import { useCityScene } from '@/lib/city/scene';
import type { CameraController } from '@/lib/map/camera';
import type { CitySignal } from '@/lib/schemas';

/**
 * The list half of list↔map sync, tested without a map.
 *
 * §5.6 makes "the list and the map cannot disagree" an acceptance criterion,
 * and the failure it names has two directions. This file covers the one jsdom
 * can see: a selection made anywhere reaches this list. The other direction —
 * clicking a row moves the reticle in the scene — is `city.spec.ts`'s claim,
 * because the reticle is in a WebGL buffer.
 */

const focusOn = vi.fn(() => true);

/** Enough of the controller for the rows to be enabled. */
const camera = { focusOn } as unknown as CameraController;

function signal(jobId: string, company: string, title: string): CitySignal {
  return {
    job_id: jobId,
    title,
    company_id: company.toLowerCase(),
    company_name: company,
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    first_seen_at: '2026-01-01T00:00:00Z',
    placement: {
      kind: 'unresolved',
      latitude: null,
      longitude: null,
      building_id: null,
      location_confidence: 'city_only',
      resolution_method: 'source_text_parse',
      stated: 'New York, NY',
      inherited: false,
      office_label: null,
      office_address: null,
    },
  } as CitySignal;
}

const CORPUS = [
  signal('a1', 'Alloy', 'Backend Engineer'),
  signal('a2', 'Alloy', 'Analyst'),
  signal('r1', 'Ramp', 'Data Engineer'),
  // Ramp is deliberately the taller column and the later name, so "most
  // openings" and "A to Z" disagree. With both orders putting the same
  // employer first, a roster holding its own fixed order would pass.
  signal('r2', 'Ramp', 'Security Engineer'),
  signal('r3', 'Ramp', 'Site Reliability Engineer'),
];

beforeEach(() => {
  focusOn.mockClear();
  useCityScene.setState({
    signals: CORPUS,
    status: { kind: 'ready' },
    sort: 'company',
    camera,
    mapReady: true,
    selected: null,
  });
});

describe('the roster', () => {
  it('lists every employer with its count', () => {
    render(<CityRoster />);

    expect(screen.getByRole('button', { name: /Alloy/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ramp/ })).toBeInTheDocument();
    expect(screen.getByText('2 employers')).toBeInTheDocument();
  });

  it('keeps the roles folded away until an employer is opened', () => {
    render(<CityRoster />);

    expect(screen.queryByRole('button', { name: 'Backend Engineer' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Alloy/ }));

    expect(screen.getByRole('button', { name: 'Backend Engineer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyst' })).toBeInTheDocument();
  });

  it('lists the roles top of the stack first, the way they are read', () => {
    render(<CityRoster />);
    fireEvent.click(screen.getByRole('button', { name: /Alloy/ }));

    const roles = screen
      .getAllByRole('button')
      .map((button) => button.textContent ?? '')
      .filter((text) => text.includes('Engineer') || text.includes('Analyst'));

    // The buffer stacks alphabetically from the bottom — Analyst, then Backend
    // Engineer — so the list reads the other way round to match the scene.
    expect(roles[0]).toContain('Backend Engineer');
  });

  it('selects a role, and lets the same click put it back', () => {
    render(<CityRoster />);
    fireEvent.click(screen.getByRole('button', { name: /Alloy/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Analyst' }));
    expect(useCityScene.getState().selected).toBe('a2');

    fireEvent.click(screen.getByRole('button', { name: 'Analyst' }));
    expect(useCityScene.getState().selected).toBeNull();
  });

  it('marks the selected role for a screen reader, not only in colour', () => {
    useCityScene.setState({ selected: 'a2' });

    render(<CityRoster />);

    expect(screen.getByRole('button', { name: 'Analyst' })).toHaveAttribute('aria-current', 'true');
  });

  it('opens the employer of a role selected somewhere else', () => {
    // The half that is easy to skip: a click on a beacon highlights a row
    // inside a collapsed group, and the list silently disagrees with the map
    // about what is being shown.
    render(<CityRoster />);
    expect(screen.queryByRole('button', { name: 'Data Engineer' })).toBeNull();

    // Wrapped because this is the whole point of the test: the change arrives
    // from outside React, the way a click on a beacon does.
    act(() => useCityScene.setState({ selected: 'r1' }));

    expect(screen.getByRole('button', { name: 'Data Engineer' })).toBeInTheDocument();
  });

  it('flies the camera to a column when its row is clicked', () => {
    render(<CityRoster />);

    fireEvent.click(screen.getByRole('button', { name: /Ramp/ }));

    expect(focusOn).toHaveBeenCalledTimes(1);
  });

  it('reorders itself with the field rather than holding its own order', () => {
    render(<CityRoster />);
    const before = screen
      .getAllByRole('button', { expanded: false })
      .map((button) => button.textContent ?? '');

    fireEvent.click(screen.getByRole('radio', { name: 'Openings' }));

    const after = screen
      .getAllByRole('button', { expanded: false })
      .map((button) => button.textContent ?? '');
    // Ramp has three roles and Alloy two, so "most openings" reverses the
    // alphabet. The list reads its ordering from the same pure function the
    // instance buffer does; a second sort here could disagree with the scene.
    expect(before[0]).toContain('Alloy');
    expect(after[0]).toContain('Ramp');
    expect(after[1]).toContain('Alloy');
  });
});
