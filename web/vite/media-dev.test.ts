// @vitest-environment node
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { createServer, request, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { mediaHandler } from "./media-dev";

let server: Server;
let base = "";
const next = vi.fn();                                   // a real spy: the handler must call it only for paths that are not /media/

beforeAll(async () => {
  const dir = mkdtempSync(join(tmpdir(), "dt-media-"));
  mkdirSync(join(dir, "assets", "clips", "a"), { recursive: true });
  writeFileSync(join(dir, "assets", "clips.json"), '{"ok":true}');
  writeFileSync(join(dir, "assets", "clips", "a", "gen.mp4"), Buffer.from("0123456789"));
  writeFileSync(join(dir, "secret.txt"), "outside");
  symlinkSync(join(dir, "secret.txt"), join(dir, "assets", "leak.txt"));        // a link INSIDE the root that leads OUT of it
  symlinkSync(join(dir, "assets"), join(dir, "linked-root"));                   // the root itself reached through a link (the scratch layout)
  server = createServer((req, res) => mediaHandler(join(dir, "linked-root"))(req, res, () => { next(); res.statusCode = 500; res.end("next was called"); }));
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(() => void server.close());
beforeEach(() => next.mockClear());

describe("media-dev middleware", () => {
  it("serves JSON with its type, no-cache, and ranges advertised, from a root reached through a symlink", async () => {
    const r = await fetch(`${base}/media/clips.json`);
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("application/json");
    expect(r.headers.get("accept-ranges")).toBe("bytes");
    expect(await r.json()).toEqual({ ok: true });
    expect(next).not.toHaveBeenCalled();
  });
  it("answers a range request with 206 and the right bytes (a <video> cannot seek without it)", async () => {
    const r = await fetch(`${base}/media/clips/a/gen.mp4`, { headers: { Range: "bytes=2-5" } });
    expect(r.status).toBe(206);
    expect(r.headers.get("content-range")).toBe("bytes 2-5/10");
    expect(await r.text()).toBe("2345");
    const tail = await fetch(`${base}/media/clips/a/gen.mp4`, { headers: { Range: "bytes=-3" } });
    expect(await tail.text()).toBe("789");
  });
  it("416 for a range past the end", async () => {
    expect((await fetch(`${base}/media/clips/a/gen.mp4`, { headers: { Range: "bytes=50-60" } })).status).toBe(416);
  });
  it("a missing file under /media/ is a 404 of its own, never a fall-through to whatever answers other paths (a home page with 200)", async () => {
    const r = await fetch(`${base}/media/missing.json`);
    expect(r.status).toBe(404);
    expect(await r.text()).toBe("not found: /media/missing.json");
    expect((await fetch(`${base}/media/clips`)).status).toBe(404);              // a directory
    expect(next).not.toHaveBeenCalled();
  });
  it("never leaves the root: dot-dot paths sent as they are (fetch would tidy them away before they arrived), and a symlink inside the root that points outside it", async () => {
    const raw = (path: string) => new Promise<{ status: number; body: string }>((resolve, reject) => {
      const url = new URL(base);
      request({ host: url.hostname, port: url.port, path }, (res) => {
        let body = "";
        res.on("data", (d) => (body += d));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      }).on("error", reject).end();
    });
    for (const p of ["/media/..%2Fsecret.txt", "/media/%2e%2e/secret.txt", "/media/../secret.txt", "/media/clips/../../secret.txt", "/media/leak.txt"]) {
      const r = await raw(p);
      expect(r.status, p).toBe(404);
      expect(r.body, p).not.toContain("outside");
    }
    expect(next).not.toHaveBeenCalled();
  });
  it("passes anything that is not /media/ on", async () => {
    expect((await fetch(`${base}/other`)).status).toBe(500);
    expect(next).toHaveBeenCalledTimes(1);
  });
});
