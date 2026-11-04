import { describe, expect, it } from "vitest";
import { hasMedia, mediaUrl, resolveBase } from "./media";

describe("media base", () => {
  it("dev with nothing set serves the local /media/ route", () => {
    expect(resolveBase({ DEV: true })).toBe("/media/");
  });
  it("VITE_MEDIA_BASE wins in dev and in production, and always ends in a slash", () => {
    expect(resolveBase({ DEV: true, VITE_MEDIA_BASE: "https://m.example/divetwin/v1" })).toBe("https://m.example/divetwin/v1/");
    expect(resolveBase({ DEV: false, VITE_MEDIA_BASE: "/media/" })).toBe("/media/");
  });
  it("a production build with no base has no media, and says so instead of guessing a host", () => {
    expect(resolveBase({ DEV: false })).toBe("");
    expect(hasMedia("")).toBe(false);
    expect(hasMedia("/media/")).toBe(true);
  });
  it("joins a path without doubling slashes", () => {
    expect(mediaUrl("clips.json", "/media/")).toBe("/media/clips.json");
    expect(mediaUrl("/clips/a/gen.mp4", "https://m.example/divetwin/v1/")).toBe("https://m.example/divetwin/v1/clips/a/gen.mp4");
  });
});
