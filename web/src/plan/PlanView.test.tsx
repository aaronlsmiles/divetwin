import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { PlanView } from "./PlanView";
import { parseClips, parsePath, parsePlan } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import { WALL_TEST_LIMIT, wallTestLimit } from "../below/text";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;
const view = (c: typeof dive, frame: number) =>
  render(<PlanView clip={c} frame={frame} path={parsePath(readFixtureJson(c.assets.path), c)} plan={parsePlan(readFixtureJson(doc.recordings[c.recording_key].plan), c.recording_key)} />);

describe("PlanView", () => {
  it("the far end's label stays inside the square: beside the wall, or over its end when it would run off (Air's longer label)", () => {
    for (const c of doc.clips) {
      const { container } = view(c, 5);
      const t = [...container.querySelectorAll("text.lbl")].find((e) => /far (wall|end)/.test(e.textContent!))!;
      const x = Number(t.getAttribute("x")), w = t.textContent!.length * 6.5;                  // 12 px Geist: about 6.5 px a character
      if (t.getAttribute("text-anchor") === "end") expect(x).toBeLessThanOrEqual(400);
      else expect(x + w).toBeLessThanOrEqual(400);
      cleanup();
    }
  });
  it("draws walls, the far wall with its measured distance, the path and a cursor", () => {
    const { container } = view(dive, 88);
    expect(container.querySelector("polyline.walls")).not.toBeNull();
    expect(container.querySelector("line.far-wall")).not.toBeNull();
    expect(screen.getByText(`far wall ${Math.round(doc.recordings["freshwater-basicEnhance"].far_end)} su`)).toBeTruthy();
    expect(container.querySelectorAll("polyline.path.ink").length).toBeGreaterThan(0);
    expect(container.querySelector("circle.cursor")).not.toBeNull();
    expect(container.querySelector("g.stop")).toBeNull();
  });
  it("in Air the far end is 'the far end as measured' (the tank's end is transparent: call 28), not a wall", () => {
    const air = doc.clips[2], rec = doc.recordings["air"];
    const { container } = view(air, 5);
    expect(screen.getByText(`far end as measured ${Math.round(rec.far_end)} su`)).toBeTruthy();
    expect(container.querySelector("svg")!.getAttribute("aria-label")).toMatch(/^The tank from above\. Far end as measured /);
    expect(container.textContent).not.toMatch(/far wall/);
    expect(container.querySelector("figcaption")!.textContent).toBe(wallTestLimit("air"));
    expect(wallTestLimit("air")).toContain("out through the far end as measured;");
  });
  it("the path is gold where D is above 3 and nowhere on a clip that never passes it", () => {
    expect(view(dive, 88).container.querySelectorAll("polyline.path.gold").length).toBeGreaterThan(0);
    cleanup();
    expect(view(calm, 40).container.querySelectorAll("polyline.path.gold")).toHaveLength(0);
  });
  it("past the cap or a loss the path stops with a marker, and the cursor stays on the last trusted point, hollow", () => {
    const a = view(pellets, 90);
    expect(a.container.querySelector("g.stop text")!.textContent).toBe(`trusted range ends · f${pellets.unverifiable_from}`);
    expect(a.container.querySelector("circle.cursor.frozen")).not.toBeNull();
    expect(a.container.querySelector("svg")!.getAttribute("aria-label")).toMatch(/unverifiable/);
    cleanup();
    expect(view(lost, 5).container.querySelector("g.stop text")!.textContent).toBe(`path lost · f${lost.lost_from}`);
  });
  it("says in words where the camera is, in su", () => {
    expect(view(dive, 88).container.querySelector("svg")!.getAttribute("aria-label")).toBe(
      `The tank from above. Far wall ${Math.round(doc.recordings["freshwater-basicEnhance"].far_end)} su. At frame 88, the camera is ${Math.round(dive.path[88][2]!)} su in.`);
  });
  it("states the wall test's limit under the drawing", () => {
    view(dive, 88);
    expect(screen.getByText(WALL_TEST_LIMIT)).toBeTruthy();
  });
});
