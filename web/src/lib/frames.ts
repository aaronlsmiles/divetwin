/** Seek target for frame f: the middle of the frame, so the decoder lands on f. */
export const timeFor = (f: number, fps: number): number => (f + 0.5) / fps;
/** The frame a mid-frame time belongs to (the inverse of timeFor). */
export const frameFromTime = (t: number, fps: number): number => Math.floor(t * fps + 1e-6);
export const clampFrame = (f: number, n: number): number => (Number.isFinite(f) ? Math.max(0, Math.min(n - 1, Math.round(f))) : 0);
/** "f88 · 3.67 s": the scrubber's readout. */
export const readout = (f: number, fps: number): string => `f${f} · ${(f / fps).toFixed(2)} s`;

export const SHIFT_STEP = 12;                   // half a second at 24 fps: the same run the departure test uses

/** The frame a key press moves to, or null for a key that is not ours. Arrows ±1, Shift ±12, Home and End. */
export function stepFrame(key: string, shift: boolean, f: number, n: number): number | null {
  const step = shift ? SHIFT_STEP : 1;
  switch (key) {
    case "ArrowRight": case "ArrowUp": return clampFrame(f + step, n);
    case "ArrowLeft": case "ArrowDown": return clampFrame(f - step, n);
    case "Home": return 0;
    case "End": return n - 1;
    default: return null;
  }
}
