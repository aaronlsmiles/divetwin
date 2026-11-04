// A fetch that answers from src/test/fixtures/, laid out like the media host (clips.json, clips/<id>/path.json, recordings/…).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { vi } from "vitest";

// Plain paths, not URL objects: under jsdom the global URL is jsdom's, which readFileSync rejects.
export const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
export const fixturePath = (rel: string) => join(FIXTURE, rel);
export const readFixtureJson = <T = any>(rel: string): T => JSON.parse(readFileSync(fixturePath(rel), "utf8")) as T;
export const readFixtureBytes = (rel: string): Uint8Array => new Uint8Array(readFileSync(fixturePath(rel)));

export const FIXTURE_IDS = [
  "freshwater-basicEnhance__gen45__N__5s",
  "saltwater-pellets__gen45__N__5s",
  "air__wan22__N__5s",
  "air__gen45__D__5s",
] as const;

/** Install the stub; returns the list of URLs asked for. Anything not in the fixtures answers 404. */
export function stubFixtureFetch(base = "/media/"): string[] {
  const asked: string[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = String(input);
    asked.push(url);
    if (!url.startsWith(base)) return new Response("not found", { status: 404 });
    try {
      const bytes = readFileSync(fixturePath(url.slice(base.length)));
      const type = url.endsWith(".json") ? "application/json" : url.endsWith(".png") ? "image/png" : "application/octet-stream";
      return new Response(bytes, { status: 200, headers: { "content-type": type } });
    } catch {
      return new Response("not found", { status: 404 });
    }
  });
  return asked;
}
