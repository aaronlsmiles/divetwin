import { useState } from "react";
import { useTheme } from "./useTheme";
import { PlainSwitch } from "../plainwords/PlainWords";

export const DOI = "10.5281/zenodo.16753748";

/** The tank from above (16 px square); an ink path enters at the bottom and leaves through the top wall. */
export function Mark() {
  return (
    <svg className="mark" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6 16 C6 11 10 10 9 6 S10 2 10 0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function TopBar() {
  const [theme, setTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <header className="bar">
      <a className="brand" href="/"><Mark /><span>Dive Twin</span></a>
      <button className="bar-menu" type="button" aria-expanded={open} aria-controls="bar-nav" onClick={() => setOpen(!open)}>Menu</button>
      <div id="bar-nav" className={`bar-nav${open ? " is-open" : ""}`}>
        <a href="#statement" onClick={() => setOpen(false)}>About this measure</a>
        <a href={`https://doi.org/${DOI}`} rel="noopener">Dataset<span className="visually-hidden"> on Zenodo (opens doi.org)</span></a>
        <PlainSwitch after={() => setOpen(false)} />
        <button type="button" className="theme-btn" onClick={() => setTheme(next)}>{next === "dark" ? "Dark" : "Light"} theme</button>
      </div>
    </header>
  );
}
