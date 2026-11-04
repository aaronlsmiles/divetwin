// "In plain words": Dive Twin's story for a bright 12-year-old, or for anyone new to the field.
// Additive: it never edits the page's own copy. The method is the hub's docs/plain-words.md; the words are the main session's
// draft (prototypes/plans/p04-dive-twin/plain-words-draft-2026-11-04.md), changed only where words.test.ts forced it.
// Every digit here comes from clips.json or the page's two thresholds, and labels from the page appear only in quotes;
// words.test.ts holds both rules, the reading level and where each note is placed.

export type Chapter = { id: string; title: string; band: string[] };

/** The trail, in reading order down the one page: "Next" walks it. Chapter 1 sits above the stage, 2 above the evidence row,
 *  3 above the statement. */
export const CHAPTERS: Chapter[] = [
  {
    id: "plain-words-1",
    title: "What this is",
    band: [
      "Here's what I was poking at.",
      "I filmed a fish tank with a camera that has two eyes, a little apart, like yours. Seeing from two places at once lets it work out how far away everything is. So I know the tank's true shape.",
      "Then I gave one photo of that tank to a computer program that makes films from a single picture. I asked it to carry on: swim in, or just keep going.",
      "The program never saw the tank. It only had the photo. So its film is a dream of the tank.",
      "One picture shows the real tank. The other shows the dream. Drag the line under them, and both move together.",
    ],
  },
  {
    id: "plain-words-2",
    title: "Same shape?",
    band: [
      "So does the dream keep the tank's shape?",
      "For every frame, I worked out how far away each spot in the dream looks. Then I checked it against the real tank, seen from the same place.",
      "The big number, \"D\", sums it up. At 1, the dream is as close to the real tank as the computer gets when it measures a real photo. At 3, the tank has changed shape.",
      "In the film the page opens on, \"D\" passes 3 just under four seconds in. The back wall opens into a corridor that isn't there.",
    ],
  },
  {
    id: "plain-words-3",
    title: "Why it matters",
    band: [
      "Here's why I care.",
      "Programs like these are sold as ways to make whole worlds, not just pictures. A world has to keep its shape when you move through it.",
      "Most tests only ask whether a film looks good. This one asks whether it keeps a real place's shape. It also shows the frame where it stops.",
      "The surprise: the dreams didn't fill the tank with things. They opened it up, and made it deeper than it is.",
      "There are 35 films here: five recordings, two programs, three kinds of request. Pick any one from the list below.",
    ],
  },
];

/** Notes pinned beside the parts that need them, by id. Each id is placed in exactly one spot on the page. */
export const NOTES = {
  "stage.real": [
    "This isn't a recording. It's the real tank, rebuilt as a 3D shape from the two-eyed camera. Then it's seen from wherever the dream's camera went.",
    "Grey means no real camera ever saw that spot. It's grey, too, where the dream has gone past what I can check.",
  ],
  "stage.heat": [
    "The colours show where the two tanks disagree. The page calls this \"the heat\".",
    "Orange means the dream has that spot too close. Blue means too far away. Dark means they agree.",
    "Grey stripes mean there's nothing real to check it against. A white outline marks something moving, like a person, and it isn't counted.",
  ],
  "stage.floor": [
    "Even on a real photo, the computer gets distances a bit wrong. This picture shows where, on the real tank.",
    "It's the same for every frame. Bright patches in \"the heat\" that sit there too are the computer's usual error, not the dream's.",
  ],
  scrubber: [
    "This line is \"D\" over time. Low and flat means the dream still matches the real tank.",
    "Where it turns gold, \"D\" has gone past 3, and the tank has changed shape.",
    "Drag along it, or press play.",
  ],
  plan: [
    "This is the tank from above, like a map. The line is where the dream's camera went.",
    "The far wall is where the real tank ends. When the line turns gold, the dream has stopped being the tank.",
    "If the line stops early, I lost track of the camera, so I stopped rather than guess.",
  ],
  "numbers.scale": [
    "The computer judges distance from a single picture, and it can't tell how big anything is. A toy car and a real car can look the same in a photo.",
    "So I stretch and slide its guess once, to fit the real tank in the first frame. The page calls this \"one scale and one shift\". After that, no more fitting.",
  ],
  "numbers.V": [
    "\"V\" is how much of the picture I can still check.",
    "It drops when the camera goes where the real one never looked, or when something moving gets in the way.",
  ],
  stereo: [
    "\"Stereo\" just means two eyes. Yours are a little apart, so each sees a slightly different picture. Your brain turns the difference into distance.",
    "The camera does the same sum.",
  ],
  relief: [
    "These are the two tanks as bumpy surfaces you can turn. Turn them to look around.",
    "Its colours are rougher than in \"the heat\", so read \"the heat\" for the details.",
  ],
} satisfies Record<string, string[]>;

export type NoteId = keyof typeof NOTES;

/** Air has no far wall: the end of its tank is glass, so stereo measures the room beyond it (call 28). In Air the plan note's
 *  far-wall sentence is swapped for this one. */
export const PLAN_FAR_AIR = "The far line is as far as the real camera could see.";
export const PLAN_FAR = NOTES.plan[1].split(". ")[0] + ".";

/** A note's paragraphs for the clip on the stage (only the plan note differs, and only in Air). */
export function noteFor(id: NoteId, condition: string): string[] {
  if (id === "plan" && condition === "air") return NOTES.plan.map((p) => p.replace(PLAN_FAR, PLAN_FAR_AIR));
  return NOTES[id];
}

export const UI = {
  label: "In plain words",
  story: "The story",
  invite: "New to this?",
  follow: "Read it in plain words", // studionephele.com's invite says "New to this? Read it in plain words"
  notNow: "Not now",
  hide: "Hide plain words",
  toggle: "Plain words",
  next: "Next",
  again: "Back to the start",
};
