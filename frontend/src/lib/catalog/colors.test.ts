import { describe, expect, it } from "vitest";

import { colorSwatch, sameColor } from "./colors";

describe("colorSwatch", () => {
  it("knows the paints of the workshop, whatever the case", () => {
    expect(colorSwatch("Gelb")).toBe("#e8b923");
    expect(colorSwatch("feuerwehrrot")).toBe("#a72920");
    expect(colorSwatch("Weiss")).toBe(colorSwatch("Weiß"));
  });

  it("mixes lighter and darker shades", () => {
    expect(colorSwatch("Hellblau")).toBe("color-mix(in oklab, #2a4f8f, white 38%)");
    expect(colorSwatch("Dunkelgrün")).toBe("color-mix(in oklab, #3d6e46, black 34%)");
  });

  it("splits a two-tone paint diagonally", () => {
    const expected = "linear-gradient(135deg, #a72920 0 50%, #f4f4f0 50% 100%)";
    expect(colorSwatch("Rot-Weiß")).toBe(expected);
    expect(colorSwatch("Rot / Weiß")).toBe(expected);
    expect(colorSwatch("Rot und Weiß")).toBe(expected);
  });

  it("gives metals a sheen and leaves unknown names without a swatch", () => {
    expect(colorSwatch("Silber")).toMatch(/^linear-gradient/);
    expect(colorSwatch("Hellsilber")).toBeNull();
    expect(colorSwatch("Gold-Rot")).toBeNull();
    expect(colorSwatch("Tarnfleck")).toBeNull();
    expect(colorSwatch("Rot-Weiß-Blau")).toBeNull();
  });
});

describe("sameColor", () => {
  it("ignores case like the backend", () => {
    expect(sameColor("gelb", "Gelb")).toBe(true);
    expect(sameColor("Gelb", "Grün")).toBe(false);
  });
});
