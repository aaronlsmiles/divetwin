import { useEffect, useState } from "react";
import type { ClipsDoc } from "./types";
import { loadClips } from "./load";

export type DocState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; doc: ClipsDoc };

/** clips.json from the media base, once. An error is a message for the page, never a blank screen. */
export function useClipsDoc(base: string, attempt = 0): DocState {
  const [state, setState] = useState<DocState>({ status: "loading" });
  useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    loadClips(base).then(
      (doc) => live && setState({ status: "ready", doc }),
      (e: unknown) => live && setState({ status: "error", message: e instanceof Error ? e.message : String(e) }),
    );
    return () => { live = false; };
  }, [base, attempt]);
  return state;
}
