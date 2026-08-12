/**
 * The camera panel, checked against a real controller.
 *
 * Not against a mocked one. The single thing worth testing here is whether the
 * button and the camera can disagree — whether the label still says "Stop orbit"
 * after a gesture has already ended the orbit — and a mocked controller would
 * answer whatever the mock was told to. So these tests build the actual
 * `CameraController` over the fake map and drive it the way a user would.
 */

import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CameraControls } from '@/components/CameraControls';
import { createCameraController, type CameraController } from '@/lib/map/camera';
import { FakeMap, stubReducedMotion } from '@/lib/map/camera.fixture';

let map: FakeMap;
let camera: CameraController;

function build(reducedMotion = false) {
  const motion = stubReducedMotion(reducedMotion);
  map = new FakeMap();
  camera = createCameraController({ map });
  render(<CameraControls camera={camera} />);
  return motion;
}

/** A click, wrapped so React has flushed by the time the assertion runs. */
function click(name: RegExp): void {
  act(() => screen.getByRole('button', { name }).click());
}

beforeEach(() => vi.useFakeTimers());

afterEach(() => {
  camera?.destroy();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the camera panel', () => {
  it('renders nothing before there is a camera', () => {
    stubReducedMotion(false);
    const { container } = render(<CameraControls camera={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('sends the camera home', () => {
    build();
    map.zoom = 17;
    click(/reset view/i);
    expect(map.of('flyTo')[0]).toMatchObject({ zoom: 13.6 });
  });

  it('starts and stops an orbit, and says which it is', () => {
    build();
    click(/^orbit$/i);
    expect(camera.orbiting).toBe(true);

    click(/stop orbit/i);
    expect(camera.orbiting).toBe(false);
    expect(screen.getByRole('button', { name: /^orbit$/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('stops claiming an orbit the moment a gesture ends one', () => {
    // The bug this exists for: the button holds its own copy of "orbiting", the
    // user grabs the map, the controller cancels the orbit, and the panel goes
    // on offering to stop something that stopped a minute ago. Clicking it then
    // starts an orbit while claiming to end one.
    build();
    click(/^orbit$/i);
    expect(screen.getByRole('button', { name: /stop orbit/i })).toBeInTheDocument();

    act(() => {
      map.container.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    });

    expect(screen.getByRole('button', { name: /^orbit$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /stop orbit/i })).not.toBeInTheDocument();
  });

  it('says so when reduced motion is on, and offers no orbit', () => {
    // Not a disabled button. The controller refuses to orbit under this
    // preference, so the button would be a control that does nothing.
    build(true);
    expect(screen.getByText(/reduced motion is on/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /orbit/i })).not.toBeInTheDocument();
  });

  it('picks the preference up when it changes under the page', () => {
    const motion = build(false);
    expect(screen.queryByText(/reduced motion is on/i)).not.toBeInTheDocument();
    act(() => motion.set(true));
    expect(screen.getByText(/reduced motion is on/i)).toBeInTheDocument();
  });

  it('lists the keys the controller actually implements', () => {
    build();
    expect(screen.queryByText('Rotate')).not.toBeInTheDocument();
    click(/keyboard/i);
    expect(screen.getByText('Shift ← →')).toBeInTheDocument();
    expect(screen.getByText('Rotate')).toBeInTheDocument();
  });
});
