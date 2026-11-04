// The layer in the page (jsdom, the four-clip fixture): asked for or not, ?plain=, remembered, every note once, the bands in order,
// Next and Hide, quotes that name real labels, and the choice carried on links into the other studio sites.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "../App";
import { clearCache } from "../data/load";
import { stubFixtureFetch } from "../test/fixtureMedia";
import { carry, initialMode, isStudioSite, KEY, LATER } from "./state";
import { CHAPTERS, NOTES, PLAN_FAR_AIR, UI } from "./words";

beforeEach(() => { clearCache(); localStorage.clear(); sessionStorage.clear(); window.history.replaceState(null, "", "/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const open = async (search = "") => {
  stubFixtureFetch("/media/");
  window.history.replaceState(null, "", `/${search}`);
  const view = render(<App />);
  await screen.findByRole("heading", { level: 1 });
  return view;
};
const bands = () => [...document.querySelectorAll<HTMLElement>(".pw-band")];
const notes = () => [...document.querySelectorAll<HTMLElement>(".pw-note")].map((n) => n.dataset.note);

describe("the choice", () => {
  it("?plain=1 and ?plain=0 win and are remembered; then the stored choice; then Not now for this visit; else unset", () => {
    expect(initialMode("?plain=1")).toBe("on");
    expect(localStorage.getItem(KEY)).toBe("on");
    expect(initialMode("")).toBe("on");
    expect(initialMode("?plain=0")).toBe("off");
    localStorage.clear();
    expect(initialMode("")).toBe("unset");
    sessionStorage.setItem(LATER, "1");
    expect(initialMode("")).toBe("off");
  });
});

describe("in the page", () => {
  it("until asked: only the invite, under the title row; no band, no note", async () => {
    await open();
    const invite = document.querySelector('[data-plain-words="invite"] .pw-invite')!;
    expect(invite.textContent).toContain("New to this?");
    expect(within(invite as HTMLElement).getByRole("button", { name: /Read it in plain words/ })).toBeTruthy();
    expect(bands()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Plain words" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("the invite turns it on: three bands in order, every note once, focus in the first band, the switch pressed", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: /Read it in plain words/ }));
    expect(localStorage.getItem(KEY)).toBe("on");
    expect(bands().map((b) => b.id)).toEqual(CHAPTERS.map((c) => c.id));
    expect(bands().map((b) => b.closest("[data-plain-words]")!.getAttribute("data-plain-words"))).toEqual(["chapter-1", "chapter-2", "chapter-3"]);
    expect(bands().map((b) => b.querySelector("h2")!.textContent)).toEqual(CHAPTERS.map((c) => c.title));
    expect(bands()[1].textContent).toContain("chapter 2 of 3");
    expect(notes().sort()).toEqual(Object.keys(NOTES).sort());
    expect(document.querySelector(".pw-invite")).toBeNull();
    expect(document.querySelectorAll("h1")).toHaveLength(1);
    await waitFor(() => expect(document.activeElement).toBe(bands()[0]));
    expect(screen.getByRole("button", { name: "Plain words" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("each note sits before (or beside) its part: the real pane, the dream, the floor map, the scrubber, the plan, the relief, V, the statement", async () => {
    await open("?plain=1");
    await waitFor(() => expect(document.querySelector(".plan")).not.toBeNull());    // the plan view loads its path first
    const before = (id: string, sel: string) => {
      const n = document.querySelector(`[data-note="${id}"]`)!, el = document.querySelector(sel)!;
      expect(n.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING, `${id} before ${sel}`).toBeTruthy();
      return n;
    };
    expect(before("stage.real", '[data-pane="real"]').parentElement!.className).toBe("panes");
    expect(before("stage.heat", '[data-pane="dream"]').parentElement!.className).toBe("panes");
    expect(before("stage.floor", "[data-floor-map]").parentElement!.classList.contains("key-strip")).toBe(true);
    // both pane notes come before both panes, so the grid's row flow sets each above its pane and the phone keeps the panes together
    expect(before("stage.heat", '[data-pane="real"]')).toBeTruthy();
    // the scrubber's note sits straight after the scrubber, so nothing comes between the panes and the line under them
    const sNote = document.querySelector('[data-note="scrubber"]')!;
    expect(sNote.previousElementSibling!.className).toBe("scrubber");
    expect(sNote.parentElement!.className).toBe("stage");
    expect(before("plan", ".plan").closest(".panel-plan")).not.toBeNull();
    expect(before("relief", ".relief").closest(".panel-relief")).not.toBeNull();
    // V's note follows its value and words, inside V's block, so the value sits under its label
    const vNote = document.querySelector('[data-note="numbers.V"]')!, vValue = document.querySelector(".numbers > div:nth-child(2) dd.num")!;
    expect(vValue.compareDocumentPosition(vNote) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(vNote.closest("dd")!.className).toBe("pw-dd");
    expect(vNote.closest(".numbers > div")).toBe(vValue.closest(".numbers > div"));
    const statement = document.getElementById("statement")!;
    const ps = [...statement.querySelectorAll(":scope > p, :scope > .pw-note")].map((e) => (e as HTMLElement).dataset.note ?? "p");
    expect(ps.slice(0, 4)).toEqual(["numbers.scale", "p", "stereo", "p"]);
    // nothing of the layer sits inside a frame
    expect(document.querySelectorAll(".pane-frame .pw-note, .relief-frame .pw-note, .plan svg .pw-note")).toHaveLength(0);
  });

  it("Next goes to the next band and focuses it; the last goes back to the start; the map lists the three", async () => {
    await open("?plain=1");
    const map = within(bands()[0].querySelector("nav")!);
    expect(map.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(CHAPTERS.map((c) => `#${c.id}`));
    expect(map.getByRole("link", { current: "step" }).textContent).toContain(CHAPTERS[0].title);
    fireEvent.click(within(bands()[0]).getByRole("link", { name: `Next: ${CHAPTERS[1].title}` }));
    expect(document.activeElement).toBe(bands()[1]);
    fireEvent.click(within(bands()[1]).getByRole("link", { name: `Next: ${CHAPTERS[2].title}` }));
    expect(document.activeElement).toBe(bands()[2]);
    fireEvent.click(within(bands()[2]).getByRole("link", { name: "Back to the start" }));
    expect(document.activeElement).toBe(bands()[0]);
    expect(window.location.hash).toBe("");
  });

  it("Hide puts it all away and drops ?plain= from the address, keeping the clip and frame; the switch brings it back", async () => {
    await open("?plain=1&clip=saltwater-pellets__gen45__N__5s&f=3");
    fireEvent.click(within(bands()[1]).getByRole("button", { name: UI.hide }));
    expect(bands()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
    expect(document.querySelector(".pw-invite")).toBeNull();
    expect(window.location.search).toBe("?clip=saltwater-pellets__gen45__N__5s&f=3");
    expect(localStorage.getItem(KEY)).toBe("off");
    fireEvent.click(screen.getByRole("button", { name: "Plain words" }));
    expect(bands()).toHaveLength(3);
  });

  it("turned on before the clips have loaded, focus still lands in the first band once it is there", async () => {
    stubFixtureFetch("/media/");
    const served = globalThis.fetch;                                                // a slow network: the clips arrive after a frame or two
    vi.stubGlobal("fetch", (...a: Parameters<typeof fetch>) => new Promise<Response>((r) => setTimeout(() => r(served(...a)), 120)));
    render(<App />);
    expect(document.querySelector("h1")).toBeNull();                                // still loading
    fireEvent.click(screen.getByRole("button", { name: "Plain words" }));
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(document.activeElement).toBe(bands()[0]));
  });

  it("Not now puts the invite away for this visit", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: UI.notNow }));
    expect(document.querySelector(".pw-invite")).toBeNull();
    expect(sessionStorage.getItem(LATER)).toBe("1");
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("every quote in the layer names a label the page really shows (in its words or what a screen reader hears)", async () => {
    const view = await open("?plain=0");
    const root = view.container;
    const seen = [root.textContent ?? "", ...[...root.querySelectorAll("[aria-label]")].map((e) => e.getAttribute("aria-label"))].join(" ").toLowerCase();
    const quotes = [...new Set([...CHAPTERS.flatMap((c) => c.band), ...Object.values(NOTES).flat()].flatMap((s) => [...s.matchAll(/"([^"]+)"/g)].map((m) => m[1])))];
    expect(quotes.length).toBeGreaterThanOrEqual(5);
    expect(quotes.filter((q) => (q.length === 1 ? !new RegExp(`\\b${q}\\b`).test(root.textContent ?? "") : !seen.includes(q.toLowerCase())))).toEqual([]);
    expect(seen).not.toContain("scale and shift");     // the draft's quote: the page says "one scale and one shift"
  });

  it("in Air the plan note never says far wall", async () => {
    await open("?plain=1&clip=air__wan22__N__5s");
    const plan = document.querySelector('[data-note="plan"]')!.textContent!;
    expect(plan).toContain(PLAN_FAR_AIR);
    expect(plan).not.toMatch(/far wall/i);
  });
});

describe("the choice travels on links into the other studio sites", () => {
  it("knows a studio site from this one and from anyone else's", () => {
    expect(isStudioSite("studionephele.com", "divetwin.studionephele.com")).toBe(true);
    expect(isStudioSite("stilldrawn.studionephele.com", "divetwin.studionephele.com")).toBe(true);
    expect(isStudioSite("divetwin.studionephele.com", "divetwin.studionephele.com")).toBe(false);
    expect(isStudioSite("notstudionephele.com", "x")).toBe(false);
    expect(isStudioSite("doi.org", "x")).toBe(false);
  });
  it("with the layer on, links into studio sites get ?plain=1 (new links too); with it off they lose it; others are left alone", async () => {
    await open("?plain=1");
    const link = (href: string) => { const a = document.createElement("a"); a.href = href; document.querySelector("main")!.appendChild(a); return a; };
    const site = link("https://studionephele.com/work?x=1"), explorer = link("https://stilldrawn.studionephele.com/explore"), doi = link("https://doi.org/10.5281/zenodo.16753748");
    await waitFor(() => expect(site.href).toBe("https://studionephele.com/work?x=1&plain=1"));
    expect(explorer.href).toBe("https://stilldrawn.studionephele.com/explore?plain=1");
    expect(doi.href).toBe("https://doi.org/10.5281/zenodo.16753748");
    fireEvent.click(within(bands()[0]).getByRole("button", { name: UI.hide }));
    await waitFor(() => expect(site.href).toBe("https://studionephele.com/work?x=1"));
    expect(explorer.href).toBe("https://stilldrawn.studionephele.com/explore");
  });
  it("carry() alone: on adds, off removes, and an already-carried link is not touched again", () => {
    const box = document.createElement("div");
    box.innerHTML = '<a href="https://studionephele.com/?plain=1">a</a><a href="https://studionephele.com/">b</a>';
    carry(true, box);
    expect([...box.querySelectorAll("a")].map((a) => a.href)).toEqual(["https://studionephele.com/?plain=1", "https://studionephele.com/?plain=1"]);
    carry(false, box);
    expect([...box.querySelectorAll("a")].map((a) => a.href)).toEqual(["https://studionephele.com/", "https://studionephele.com/"]);
  });
});
