import { describe, expect, it } from "vitest";

import { countLines, countMessage, lying, placesLine } from "./stock";

const place = (quantity: number, name: string) => ({ code: name, place: name, quantity });

describe("stock by number", () => {
  it("names where a model lies, the most first and the rest as a number", () => {
    expect(placesLine([place(7, "Regal 2, Boden 3")])).toBe("7 · Regal 2, Boden 3");
    expect(placesLine([place(7, "Regal 2, Boden 3"), place(2, "Regal 1"), place(1, "Packtisch")])).toBe(
      "7 · Regal 2, Boden 3; 2 · Regal 1 + 1 weiterer Platz",
    );
    expect(placesLine([])).toBe("");
  });

  it("counts free and reserved pieces as lying there", () => {
    expect(lying({ free: 3, reserved: 2 })).toBe(5);
  });

  it("books only the lines that changed", () => {
    expect(
      countLines([
        { variantId: "v1", locationCode: "R01-B01", expected: 3, counted: 3 },
        { variantId: "v2", locationCode: "R01-B01", expected: 3, counted: 1 },
      ]),
    ).toEqual([{ variant_id: "v2", location_code: "R01-B01", expected: 3, counted: 1 }]);
  });

  it("says what a count booked", () => {
    expect(countMessage({ missing: 0, added: 0, reserved: 0 })).toBe("Alles stimmt, nichts gebucht.");
    expect(countMessage({ missing: 2, added: 1, reserved: 1 })).toBe(
      "2 fehlende Stücke ausgebucht, 1 Stück dazu eingebucht, 1 davon gleich für wartende Bestellungen reserviert.",
    );
  });
});
