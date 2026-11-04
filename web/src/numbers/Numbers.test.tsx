import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { Numbers } from "./Numbers";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;
const row = (name: string) => within(screen.getByText(name, { selector: "dt" }).parentElement as HTMLElement);

describe("Numbers", () => {
  it("D now leads, gold only while above 3", () => {
    render(<Numbers doc={doc} clip={dive} frame={100} />);
    const lead = document.querySelector(".lead") as HTMLElement;
    expect(lead.textContent).toBe(dive.D[100]!.toFixed(2));
    expect(lead.classList.contains("is-gold")).toBe(true);
    cleanup();
    render(<Numbers doc={doc} clip={dive} frame={10} />);
    expect(document.querySelector(".lead.is-gold")).toBeNull();
    cleanup();
    render(<Numbers doc={doc} clip={calm} frame={40} />);
    expect(document.querySelector(".is-gold")).toBeNull();
  });
  it("gives the floor in words, from the recording's own numbers", () => {
    render(<Numbers doc={doc} clip={dive} frame={88} />);
    const rec = doc.recordings["freshwater-basicEnhance"];
    const note = document.querySelector(".n-lead .n-note")!.textContent!;
    expect(note).toContain("1 = no worse than mono depth on the real tank");
    expect(note).toContain("mono depth's own error on the real frames of Freshwater, enhanced, is");
    expect(note).not.toMatch(/'s real frames/);
    expect(note).toContain(rec.floor.toFixed(3));
    expect(note).toContain(rec.null_dream_D.median.toFixed(2));
  });
  it("says what V is: the rebuilt tank's coverage, leaving out a tracked moving object", () => {
    render(<Numbers doc={doc} clip={dive} frame={88} />);
    expect(row("V now").getByText(/the share of the frame the rebuilt tank covers, leaving out a tracked moving object/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/a real camera also saw/);
  });
  it("V, distance against the far end, departure and agreement for the default clip", () => {
    render(<Numbers doc={doc} clip={dive} frame={88} />);
    expect(row("V now").getByText(dive.verified[88]!.toFixed(2))).toBeTruthy();
    const dist = screen.getByText("Forward distance", { selector: "dt" }).parentElement!.textContent!.replace(/\u202f/g, " ");
    expect(dist).toContain(`${Math.round(dive.path[88][2]!)} su`);
    expect(dist).toContain(`The far end as measured is at ${Math.round(dive.far_end!)} su`);
    expect(dist).toContain(`Straight-line travel to the last trusted frame: ${Math.round(dive.travel)} su`);
    expect(dist).not.toContain("whole clip");
    expect(dist).not.toMatch(/travelled/i);
    expect(row("Departure").getByText("f88 · 3.67 s")).toBeTruthy();
    expect(row("Path agreement").getByText(/% of max\(travel, 200 su\)/)).toBeTruthy();
    expect(row("Departure").getByText("D above 3 for 12 frames running (half a second)")).toBeTruthy();
    expect(row("Path agreement").getByText(/The second estimate almost always does worse than assuming a still camera, so a wide gap mostly measures that estimate failing, not doubt about the main path\./)).toBeTruthy();
  });
  it("past a cap every reading says unverifiable (V is never 0.00) and path agreement has nothing to say", () => {
    render(<Numbers doc={doc} clip={pellets} frame={pellets.unverifiable_from! + 5} />);
    expect(document.querySelector(".lead")!.textContent).toBe("unverifiable");
    expect(row("V now").getByText("unverifiable")).toBeTruthy();
    expect(row("Forward distance").getByText("unverifiable")).toBeTruthy();
    expect(row("Path agreement").getByText("unverifiable")).toBeTruthy();
    expect(row("Departure").getByText("none")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/0\.00/);
    const reason = `the dream passed the recording's trusted range (${Math.round(pellets.trusted_travel_su!)} su)`;
    expect(document.querySelector(".n-lead .n-note")!.textContent).toContain(`. The${reason.slice(3)}.`);   // a sentence starts with a capital
    const vNote = row("V now").getByText(reason, { selector: ".n-note" });
    expect(vNote.textContent, "the value already says unverifiable").toBe(reason);
  });
  it("a lost path says why", () => {
    render(<Numbers doc={doc} clip={lost} frame={lost.lost_from! + 3} />);
    expect(document.querySelector(".n-lead .n-note")!.textContent).toContain(". The camera path was lost.");
  });
});
