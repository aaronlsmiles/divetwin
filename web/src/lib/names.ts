// Short names for the page. A recording is the condition's short name, never the dataset's long file name (docs/DESIGN.md).
export const CONDITION_NAMES: Record<string, string> = {
  air: "Air",
  freshwater: "Freshwater",
  "freshwater-basicEnhance": "Freshwater, enhanced",
  saltwater: "Saltwater",
  "saltwater-pellets": "Saltwater, pellets",
};
export const ENGINE_NAMES: Record<string, string> = { gen45: "Gen-4.5", wan22: "Wan 2.2" };

export const conditionName = (key: string): string => CONDITION_NAMES[key] ?? key;
export const engineName = (key: string): string => ENGINE_NAMES[key] ?? key;

/** What the far end of a tank is called. In Air the end of the tank is transparent and stereo measures the room beyond it (call 28),
 *  so it is "the far end as measured", not a wall. */
export const farEndLabel = (condition: string): string => (condition === "air" ? "far end as measured" : "far wall");

/** The three frozen prompts (pipeline/prompts.py) in a word: the picker's legend names the chosen one, a tooltip names all three. */
export const PROMPT_WORDS: Record<string, string> = { D: "dive", B: "continue", N: "documentary" };
