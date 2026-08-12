import '@testing-library/jest-dom/vitest';

/**
 * jsdom has no 2D canvas, and says so very loudly.
 *
 * `HTMLCanvasElement.getContext` is unimplemented without the optional `canvas`
 * package. jsdom reports that through its virtual console *and then* throws, so
 * code that handles the absence perfectly well — `paintAtlas` returns null and
 * the city loses its name plates, which is the documented degradation — still
 * fills the test output with stack traces. Real failures then have to be found
 * among them.
 *
 * Returning null is what the DOM specifies for a context type the canvas cannot
 * provide, so this makes jsdom answer the way a browser without 2D support
 * would, rather than pretending a canvas exists. Nothing here paints: the
 * atlas's *pixels* are checked in `city.spec.ts`, where there is a real one.
 *
 * Deliberately not the `canvas` npm package. It is a native build on the
 * critical path of `make setup`, and it would buy one assertion that a browser
 * test already makes better.
 */
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext'];

/**
 * jsdom has no layout, so it has no `scrollIntoView` either.
 *
 * Unlike `getContext` this is not a capability a real browser can be without —
 * it is on every engine — so guarding the call in product code would be dead
 * code shipped to defend against a test environment. A no-op here is the
 * honest stand-in: there is no scrolling to do because there is nothing laid
 * out to scroll. That the panel and the selected row actually come into view is
 * a claim for `city.spec.ts`, where there is a viewport.
 */
Element.prototype.scrollIntoView = function scrollIntoView(): void {};
