import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ReliefPanel, reliefLabel } from "./ReliefPanel";
import { clearCache, parseClips } from "../data/load";
import { RELIEF_NO_WEBGL, RELIEF_NOTE } from "../below/text";
import { readFixtureJson } from "../test/fixtureMedia";
import { atlasBytes, stubReliefFetch, tankBytes } from "../test/syntheticRelief";

const doc = parseClips(readFixtureJson("clips.json"));
const dive = doc.clips[0], pellets = doc.clips[1];
afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearCache(); });

const media = (reduced: boolean, phone: boolean) => vi.stubGlobal("matchMedia", (q: string) => ({
  matches: (q.includes("reduced-motion") && reduced) || (q.includes("max-width") && phone), media: q,
  addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false, onchange: null,
}));

describe("ReliefPanel falls back to a still", () => {
  it("when WebGL will not start: a still, no orbit button, and it says why", async () => {
    stubReliefFetch(doc, dive); media(false, false);
    render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" webgl={false} />);
    const still = await screen.findByRole("img", { name: /gap between the dream and the tank at frame 0/ });
    expect(still.getAttribute("aria-label")!.startsWith("Colour: the gap as placed, not the heat.")).toBe(true);
    expect(still.getAttribute("aria-label")).toContain("A tracked moving object is not outlined here.");
    expect(screen.queryByRole("button", { name: /Orbit/ })).toBeNull();
    expect(screen.getByText(new RegExp(RELIEF_NO_WEBGL))).toBeTruthy();
    expect(document.querySelector("[data-live]")).toBeNull();
  });
  it("with reduced motion: a still, and the orbit only if asked for", async () => {
    stubReliefFetch(doc, dive); media(true, false);
    render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" webgl />);
    await screen.findByRole("img", { name: /gap between/ });
    expect(screen.getByRole("button", { name: "Orbit the surfaces" })).toBeTruthy();
    expect(document.querySelector("[data-live]")).toBeNull();
  });
  it("on a phone: a still until tapped", async () => {
    stubReliefFetch(doc, dive); media(false, true);
    render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" webgl />);
    await screen.findByRole("img", { name: /gap between/ });
    expect(screen.getByRole("button", { name: "Orbit the surfaces" })).toBeTruthy();
    expect(document.querySelector("[data-live]")).toBeNull();
  });
  it("on a desktop with WebGL it goes live (the canvas itself is checked in the browser, e2e)", async () => {
    stubReliefFetch(doc, dive); media(false, false);
    render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" webgl />);
    await vi.waitFor(() => expect(document.querySelector("[data-live]")).not.toBeNull());
    expect(screen.getByText(RELIEF_NOTE)).toBeTruthy();
  });
  it("asks the browser about WebGL once, however many frames are drawn (every probe is a context, and browsers cap them)", async () => {
    stubReliefFetch(doc, dive); media(false, true);
    const probe = vi.spyOn(HTMLCanvasElement.prototype, "getContext");
    const view = render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" />);
    await screen.findByRole("img", { name: /gap between/ });
    for (let f = 1; f < 8; f++) view.rerender(<ReliefPanel doc={doc} clip={dive} frame={f} base="/media/" />);
    const asked = probe.mock.calls.filter(([kind]) => kind === "webgl2" || kind === "webgl").length;
    expect(asked).toBeLessThanOrEqual(2);                       // one probe: webgl2, then webgl
    probe.mockRestore();
  });
  it("the label of the still and of the canvas both lead with what the colour is, and say a tracked object is not outlined", () => {
    for (const what of ["a still", "the surfaces, which can be turned by dragging"]) {
      const l = reliefLabel(7, what);
      expect(l.startsWith("Colour: the gap as placed, not the heat.")).toBe(true);
      expect(l).toContain("at frame 7");
      expect(l.endsWith("A tracked moving object is not outlined here.")).toBe(true);
    }
  });
  it("a missing atlas is a message, not a blank panel", async () => {
    vi.stubGlobal("fetch", async () => new Response("no", { status: 404 }));
    media(false, false);
    render(<ReliefPanel doc={doc} clip={dive} frame={0} base="/media/" webgl />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/atlas could not be loaded/);
  });
  it("past a cap the dream is not placed, and the caption and the label say so, with the frame and the reason", async () => {
    const tank = tankBytes(doc, dive), atlas = atlasBytes(pellets, tank);   // the fixture holds one real tank cell; the clips share it here
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/media/" + pellets.assets.relief) return new Response(atlas as BodyInit, { status: 200 });
      if (url === "/media/" + pellets.assets.tank_relief) return new Response(tank as BodyInit, { status: 200 });
      return new Response("nope", { status: 404 });
    });
    media(false, false);
    const u = pellets.unverifiable_from!;
    const said = `From frame ${u}: the dream passed the recording's trusted range (${Math.round(pellets.trusted_travel_su!)} su). Only the real tank is drawn; the dream is not placed.`;
    render(<ReliefPanel doc={doc} clip={pellets} frame={u + 5} base="/media/" webgl={false} />);
    const still = await screen.findByRole("img", { name: /gap between the dream and the tank/ });
    expect(still.getAttribute("aria-label")).toContain(said);
    expect(document.querySelector(".relief > p")!.textContent!.startsWith(said)).toBe(true);
    expect(reliefLabel(u + 5, "a still", said).endsWith(`${said} A tracked moving object is not outlined here.`)).toBe(true);
  });
  it("before the cap nothing is said about placing", async () => {
    stubReliefFetch(doc, dive); media(false, false);
    render(<ReliefPanel doc={doc} clip={dive} frame={100} base="/media/" webgl={false} />);
    const still = await screen.findByRole("img", { name: /gap between/ });
    expect(still.getAttribute("aria-label")).not.toMatch(/not placed/);
    expect(document.body.textContent).not.toMatch(/not placed/);
  });
});
