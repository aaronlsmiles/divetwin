import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { mediaDev } from "./vite/media-dev.ts";

// runs/assets is gitignored (about 250 MB). Dev and preview serve it at /media/; DIVETWIN_ASSETS points elsewhere.
const ASSETS = process.env.DIVETWIN_ASSETS ?? fileURLToPath(new URL("../runs/assets", import.meta.url));

export default defineConfig({
  plugins: [react(), mediaDev(ASSETS)],
  // Pre-bundled up front, so the dev server never discovers one mid-run and reloads the page under a test (d3-array comes in through
  // d3-scale and needs no entry of its own).
  optimizeDeps: { include: ["fast-png", "d3-scale", "d3-shape", "three", "@react-three/fiber"] },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}", "vite/**/*.test.ts"],
    setupFiles: ["src/test/setup.ts"],
  },
});
