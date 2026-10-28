/*
 * A colour name as the workshop writes it ("Gelb", "Hellblau", "Rot-Weiß") turned into a
 * paint swatch. The tones follow the RAL shades of the real vehicles (Feuerwehrrot,
 * Postgelb, Kommunalorange), not the screen primaries. A name the table does not know
 * gets no swatch; the shop then shows the name alone.
 */

const PAINT: Readonly<Record<string, string>> = {
  rot: "#a72920",
  feuerwehrrot: "#a72920",
  weinrot: "#6d2330",
  bordeaux: "#6d2330",
  orange: "#e0672a",
  kommunalorange: "#e0672a",
  gelb: "#e8b923",
  postgelb: "#f2b400",
  ocker: "#b98a37",
  beige: "#d6c3a0",
  sand: "#cdb88e",
  elfenbein: "#ebe2c8",
  creme: "#efe6cf",
  braun: "#6b4a2f",
  grün: "#3d6e46",
  olivgrün: "#4f5538",
  oliv: "#4f5538",
  khaki: "#8f8a5f",
  türkis: "#2a8c8c",
  petrol: "#1f5a63",
  blau: "#2a4f8f",
  enzianblau: "#1d4e8f",
  violett: "#6b4c8a",
  rosa: "#d98ca0",
  grau: "#8a8d8f",
  anthrazit: "#3b3f42",
  schwarz: "#1d1d1b",
  weiß: "#f4f4f0",
  silber: "linear-gradient(135deg, #e6e8ea 0%, #a9adb1 45%, #d9dcdf 60%, #8f9397 100%)",
  gold: "linear-gradient(135deg, #f0d98a 0%, #b88a2c 45%, #e3c36b 60%, #9c7424 100%)",
  kupfer: "linear-gradient(135deg, #e7a27a 0%, #a5532c 45%, #d98a62 60%, #8a4423 100%)",
};

/** Lighter and darker shades by name: "Hellblau", "Dunkelgrün". */
const SHADE: Readonly<Record<string, string>> = {
  hell: "white 38%",
  dunkel: "black 34%",
};

const solid = (paint: string | null | undefined): paint is string =>
  paint !== null && paint !== undefined && !paint.includes("gradient");

function tone(word: string): string | null {
  // "Weiss" is how a keyboard without ß writes "Weiß".
  const name = word.trim().toLocaleLowerCase("de-DE").replaceAll("ss", "ß");
  const paint = PAINT[name];
  if (paint) {
    return paint;
  }
  for (const [prefix, mix] of Object.entries(SHADE)) {
    const base = name.startsWith(prefix) ? PAINT[name.slice(prefix.length)] : undefined;
    if (solid(base)) {
      return `color-mix(in oklab, ${base}, ${mix})`;
    }
  }
  return null;
}

/**
 * The CSS background of a colour's swatch, or null for a name without one. Two colours
 * ("Rot-Weiß", "Blau/Grau", "Rot und Weiß") give a diagonally split two-tone swatch.
 */
export function colorSwatch(name: string): string | null {
  const parts = name.split(/\s*(?:-|\/|\s+und\s+)\s*/i).filter((part) => part !== "");
  if (parts.length === 1) {
    return tone(parts[0] ?? "");
  }
  const [first, second] = parts.map(tone);
  return parts.length === 2 && solid(first) && solid(second)
    ? `linear-gradient(135deg, ${first} 0 50%, ${second} 50% 100%)`
    : null;
}

/** Colours compare like in the backend: "gelb" and "Gelb" are the same paint. */
export function sameColor(a: string, b: string): boolean {
  return a.toLocaleLowerCase("de-DE") === b.toLocaleLowerCase("de-DE");
}

/** Suggestions for the colour field, the paints of the workshop most often used. */
export const PAINT_SUGGESTIONS: readonly string[] = [
  "Rot",
  "Feuerwehrrot",
  "Orange",
  "Gelb",
  "Postgelb",
  "Beige",
  "Elfenbein",
  "Braun",
  "Grün",
  "Hellgrün",
  "Olivgrün",
  "Blau",
  "Hellblau",
  "Grau",
  "Hellgrau",
  "Anthrazit",
  "Schwarz",
  "Weiß",
  "Silber",
  "Rot-Weiß",
  "Blau-Weiß",
];
