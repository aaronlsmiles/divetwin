// jsdom has no matchMedia; the theme hook reads it. Default: light, no change events.
// (vite/*.test.ts run in the node environment, where there is no window.)
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// jsdom does not implement media playback: no-ops keep the components from logging "not implemented" on every mount.
if (typeof HTMLMediaElement !== "undefined") {
  HTMLMediaElement.prototype.load = () => {};
  HTMLMediaElement.prototype.pause = () => {};
  HTMLMediaElement.prototype.play = () => Promise.resolve();
}
if (typeof HTMLCanvasElement !== "undefined") {
  // jsdom has no canvas: no context, silently (the relief and its still guard for null)
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
}
