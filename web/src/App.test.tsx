import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { clearCache } from "./data/load";
import { stubFixtureFetch } from "./test/fixtureMedia";

beforeEach(() => { clearCache(); window.history.replaceState(null, "", "/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); delete document.documentElement.dataset.theme; });

describe("shell", () => {
  it("renders an h1 and the theme toggle, which switches data-theme", async () => {
    stubFixtureFetch("/media/");
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: /Freshwater, enhanced/ });
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

describe("the page opens on the finding", () => {
  it("shows the default clip, its finding line, the stage and the scrubber parked on the departure", async () => {
    stubFixtureFetch("/media/");
    render(<App />);
    expect(screen.getByRole("status").textContent).toMatch(/Loading/);
    await screen.findByRole("heading", { level: 1, name: "Freshwater, enhanced · Gen-4.5 · prompt N · 5 s" });
    expect(screen.getByText("D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00)")).toBeTruthy();
    expect((screen.getByRole("slider", { name: "Frame" }) as HTMLInputElement).value).toBe("88");
    expect(document.title).toBe("Freshwater, enhanced · Gen-4.5 · prompt N · 5 s · Dive Twin");
    expect([...document.querySelectorAll("h1 .crumb")].map((c) => c.textContent)).toEqual(["Freshwater, enhanced ·", "Gen-4.5 ·", "prompt N ·", "5 s"]);   // a separator ends the crumb before it
    expect(document.querySelector("h1")!.textContent).toBe("Freshwater, enhanced · Gen-4.5 · prompt N · 5 s");
    expect(document.querySelectorAll("video")).toHaveLength(3);
  });

  it("follows ?clip= and ?f= from the URL", async () => {
    stubFixtureFetch("/media/");
    window.history.replaceState(null, "", "/?clip=saltwater-pellets__gen45__N__5s&f=3");
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: /Saltwater, pellets/ });
    expect((screen.getByRole("slider", { name: "Frame" }) as HTMLInputElement).value).toBe("3");
    expect(screen.getByText(/^Verification ran out at frame 20/)).toBeTruthy();
  });

  it("a failed load is a message with a way to try again, not a blank page", async () => {
    stubFixtureFetch("/elsewhere/");
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not be loaded/);
    expect(alert.textContent).toMatch(/\/media\/clips.json: 404/);
    stubFixtureFetch("/media/");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: /Freshwater, enhanced/ })).toBeTruthy());
  });
});

describe("the evidence row's reading order follows its layout", () => {
  const panels = () => [...document.querySelectorAll(".evidence > .panel")].map((p) => p.querySelector("h2")!.textContent);
  it("on a desktop: the plan view, the relief, the numbers", async () => {
    stubFixtureFetch("/media/");
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: /Freshwater, enhanced/ });
    expect(panels()).toEqual(["Where the camera went", "The two tanks as surfaces", "The numbers"]);
  });
  it("on a phone the numbers come first in the DOM itself (no CSS order, so Tab and a screen reader meet them first too)", async () => {
    stubFixtureFetch("/media/");
    const real = window.matchMedia;
    vi.stubGlobal("matchMedia", (q: string) => ({ ...real(q), matches: q === "(max-width: 760px)" || q === "(max-width: 640px)", media: q,
      addEventListener() {}, removeEventListener() {} }));
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: /Freshwater, enhanced/ });
    expect(panels()).toEqual(["The numbers", "Where the camera went", "The two tanks as surfaces"]);
    expect(document.querySelectorAll(".picker select")).toHaveLength(3);
  });
});
