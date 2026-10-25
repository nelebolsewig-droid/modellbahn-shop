import { describe, expect, it } from "vitest";

import {
  centsToEuroInput,
  dimensionsLine,
  formatGrams,
  formatMillimetres,
  formatPrice,
  formatProductNumber,
  parseEuroToCents,
  scaleSpec,
} from "./format";

describe("catalogue numbers", () => {
  it("formats prices, lengths and weights the German way", () => {
    // Intl puts a no-break space before the euro sign.
    expect(formatPrice(4990).replace(/\s/g, " ")).toBe("49,90 €");
    expect(formatPrice(123456).replace(/\s/g, " ")).toBe("1.234,56 €");
    expect(formatMillimetres(112.5)).toBe("112,5 mm");
    expect(formatMillimetres(64)).toBe("64 mm");
    expect(formatGrams(1250)).toBe("1.250 g");
  });

  it("writes the product number with six digits", () => {
    expect(formatProductNumber(42)).toBe("MB-000042");
  });

  it("builds the technical line of a scale", () => {
    expect(scaleSpec({ name: "H0", ratio: "1:87", track_gauge_mm: 16.5 })).toEqual(["H0", "1:87", "Gleis 16,5 mm"]);
    expect(scaleSpec({ name: "1:24", ratio: "1:24", track_gauge_mm: null })).toEqual(["1:24"]);
  });

  it("lists only the known dimensions", () => {
    expect(dimensionsLine({ length_mm: 112.5, width_mm: null, height_mm: 51 })).toEqual([
      "L 112,5 mm",
      "H 51 mm",
    ]);
  });
});

describe("parseEuroToCents", () => {
  it.each([
    ["49,90", 4990],
    ["49.9", 4990],
    ["49", 4900],
    [" 1.234,50 € ", 123450],
    ["0", 0],
  ])("reads %s", (input, cents) => {
    expect(parseEuroToCents(input)).toBe(cents);
  });

  it.each(["", "abc", "49,999", "-5", "4,9,0"])("refuses %s", (input) => {
    expect(parseEuroToCents(input)).toBeNull();
  });

  it("round-trips the admin input", () => {
    expect(centsToEuroInput(4990)).toBe("49,90");
    expect(parseEuroToCents(centsToEuroInput(105))).toBe(105);
  });
});
