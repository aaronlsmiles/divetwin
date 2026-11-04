import { defineConfig } from "@playwright/test";

// The port is the repo's 5299 unless E2E_PORT says otherwise (a scratch copy, or a second checkout, uses another).
const PORT = Number(process.env.E2E_PORT ?? 5299);
const sizes = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }];
const schemes = ["light", "dark"] as const;

// Data source: the REAL runs/assets (about 250 MB, gitignored), served by the dev server at /media/ (vite/media-dev.ts).
// No fixture stands in here; the specs skip, saying so, if /media/clips.json is not there.
// --force rebuilds the pre-bundled dependencies on every start, so a stale cache never reloads the page in the middle of a test.
export default defineConfig({
  testDir: ".",
  timeout: 45_000,
  fullyParallel: true,
  reporter: [["list"]],
  webServer: { command: `npx vite --port ${PORT} --strictPort --force`, port: PORT, reuseExistingServer: false, cwd: ".." },
  use: { baseURL: `http://localhost:${PORT}` },
  projects: sizes.flatMap((s) => schemes.map((c) => ({
    name: `${s.name}-${c}`,
    use: { viewport: { width: s.width, height: s.height }, colorScheme: c, hasTouch: s.name === "phone" },
  }))),
});
