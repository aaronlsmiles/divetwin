import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Band, ANSWER, surprises } from "./Band";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import { tally, tallyWords } from "../lib/tally";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));

describe("the findings band (hub call 92)", () => {
  it("says the answer once, as a statement and not a heading, and no heading on the page is a second h1", () => {
    render(<Band clips={doc.clips} onShow={() => {}} />);
    expect(screen.getByText(ANSWER).tagName).toBe("P");
    expect(screen.queryAllByRole("heading", { level: 1 })).toHaveLength(0);
    expect(ANSWER).toBe("A dream can be checked against the real tank frame by frame, until it leaves what was measured.");
    expect(ANSWER).not.toMatch(/\d/);
  });

  it("the tally is the finding classification's counts, each a button named by its visible words", () => {
    render(<Band clips={doc.clips} onShow={() => {}} />);
    const group = screen.getByRole("group", { name: `The ${doc.clips.length} clips, by their finding line` });
    const buttons = within(group).getAllByRole("button");
    const t = tally(doc.clips);
    expect(buttons.map((b) => b.textContent)).toEqual(t.map((g) => `${g.n} ${tallyWords(g.kind, g.n)}`));
    for (const b of buttons) {
      // label in name: the accessible name starts with what is seen, then says what the button does
      expect(b.getAttribute("aria-label")).toBe(`${b.textContent}: show them in the clip table`);
    }
  });

  it("a count brings its clips forward: it hands its kind to the page", () => {
    const onShow = vi.fn();
    render(<Band clips={doc.clips} onShow={onShow} />);
    fireEvent.click(screen.getByRole("button", { name: /^2 can't be checked to the end/ }));
    expect(onShow).toHaveBeenCalledWith("unchecked");
  });

  it("the two surprises, in the page's technical voice, with the threshold and V taken from the code and the data", () => {
    const s = surprises(doc.clips);
    expect(s.map((x) => `${x.lead} ${x.rest}`)).toEqual([
      "Dreams open the tank up: in every clip past 3, the invented space reads farther than the real tank.",
      "Only D sees a dream leave: the Gen-4.5 clips past 3 keep V at 1.00; the rebuilt tank still covers the frame.",
    ]);
    render(<Band clips={doc.clips} onShow={() => {}} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("the second surprise is left out when the data no longer bears it out (no engine keeps V at 1.00 past 3)", () => {
    const fallen = doc.clips.map((c) => (c.first_D3 === null ? c : { ...c, verified: c.verified.map((v, i) => (i === 100 ? 0.7 : v)) }));
    expect(surprises(fallen).map((x) => x.lead)).toEqual(["Dreams open the tank up:"]);
  });

  it("nothing in the band is gold, and nothing is pencil", () => {
    const { container } = render(<Band clips={doc.clips} onShow={() => {}} />);
    expect(container.innerHTML).not.toMatch(/gold|pencil|pw-/);
  });
});
