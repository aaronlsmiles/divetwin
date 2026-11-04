// Dev and preview only: serve runs/assets at /media/, laid out as on the media host (divetwin/v1/…).
// Range-aware, because a <video> cannot seek without 206s. The pattern is the StillDrawn Explorer's vite/media-dev.ts, with two
// changes: it follows a symlinked root (the scratch layout points runs/assets at the real folder) but never lets a file inside the
// root lead out of it (every path is realpath'd and compared), and any /media/ path it cannot serve is a 404 of its own, never
// a fall-through to the dev server's home page (which would answer 200 with HTML to a missing clips.json).
import { createReadStream, realpathSync, statSync } from "node:fs";
import { extname, resolve, sep } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

const TYPES: Record<string, string> = {
  ".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json",
};

export function mediaHandler(root: string) {
  return (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    let url: string;
    try { url = decodeURIComponent((req.url ?? "").split("?")[0]); } catch { return next(); }
    if (!url.startsWith("/media/")) return next();
    const notFound = () => { res.statusCode = 404; res.setHeader("Content-Type", "text/plain"); res.end(`not found: ${url}`); };
    let file: string, size: number;
    try {
      const top = realpathSync(resolve(root));
      file = realpathSync(resolve(top, "." + url.slice("/media".length)));      // a link inside the root that leads out is refused here
      if (!file.startsWith(top + sep)) return notFound();
      const st = statSync(file);
      if (!st.isFile()) return notFound();
      size = st.size;
    } catch {
      return notFound();
    }
    res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
    res.setHeader("Accept-Ranges", "bytes");
    res.setHeader("Cache-Control", "no-cache");
    const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
    if (m && (m[1] || m[2])) {
      const start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2]));
      const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
      if (start > end || start >= size) {
        res.statusCode = 416;
        res.setHeader("Content-Range", `bytes */${size}`);
        return void res.end();
      }
      res.statusCode = 206;
      res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
      res.setHeader("Content-Length", String(end - start + 1));
      return void createReadStream(file, { start, end }).pipe(res);
    }
    res.setHeader("Content-Length", String(size));
    createReadStream(file).pipe(res);
  };
}

export function mediaDev(root: string): Plugin {
  return {
    name: "media-dev",
    apply: (_config, env) => env.command === "serve" || env.isPreview === true,
    configureServer: (server) => void server.middlewares.use(mediaHandler(root)),
    configurePreviewServer: (server) => void server.middlewares.use(mediaHandler(root)),
  };
}
