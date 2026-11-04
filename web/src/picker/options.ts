import type { Clip } from "../data/types";

export interface Dims { condition: string; engine: string; prompt: string; seconds: number }
export const dimsOf = (c: Clip): Dims => ({ condition: c.condition, engine: c.engine, prompt: c.prompt, seconds: c.seconds });

/** The distinct values of one dimension, in the order the file lists them (the pipeline's own order). */
export function valuesOf<K extends keyof Dims>(clips: Clip[], key: K): Dims[K][] {
  return [...new Set(clips.map((c) => dimsOf(c)[key]))];
}

/** The lengths that exist for this recording, engine and prompt: the 5 s / 10 s switch shows only if there is more than one. */
export const lengthsFor = (clips: Clip[], cur: Clip): number[] =>
  clips.filter((c) => c.condition === cur.condition && c.engine === cur.engine && c.prompt === cur.prompt).map((c) => c.seconds).sort((a, b) => a - b);

/**
 * The clip after changing one dimension. Exact match first; if that combination does not exist (a 10 s dive under another prompt,
 * say) the same recording, engine and prompt at the nearest length, preferring the shortest; never a dead end.
 */
export function resolve(clips: Clip[], cur: Clip, change: Partial<Dims>): Clip {
  const want = { ...dimsOf(cur), ...change };
  const hit = clips.find((c) => c.condition === want.condition && c.engine === want.engine && c.prompt === want.prompt && c.seconds === want.seconds);
  if (hit) return hit;
  const sameTrio = clips.filter((c) => c.condition === want.condition && c.engine === want.engine && c.prompt === want.prompt);
  if (sameTrio.length) return [...sameTrio].sort((a, b) => a.seconds - b.seconds)[0];
  return clips.find((c) => Object.entries(change).every(([k, v]) => dimsOf(c)[k as keyof Dims] === v)) ?? cur;
}
