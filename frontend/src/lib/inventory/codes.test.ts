import { describe, expect, it } from "vitest";

import {
  ALPHABET,
  checkCharacter,
  formatUnitCode,
  interpretations,
  isValidEan13,
  isValidUnitCode,
  normalizeUnitCode,
} from "./codes";

// Made by the backend (new_unit_code): both sides must agree on the check character.
const FROM_BACKEND = ["J4WZXRT2S2", "XKAQ0EDJN2", "4NNYRWPX5S", "M5N7HHNG3B", "Y1B0RV1H37"];
const CODE = "7KQ2X9F4MZ";

describe("unit codes", () => {
  it("agrees with the backend on the check character", () => {
    expect(checkCharacter("7KQ2X9F4M")).toBe("Z");
    for (const code of FROM_BACKEND) {
      expect(isValidUnitCode(code), code).toBe(true);
    }
  });

  it("catches every single wrong character", () => {
    for (let position = 0; position < 10; position += 1) {
      for (const char of ALPHABET) {
        if (char !== CODE[position]) {
          const wrong = CODE.slice(0, position) + char + CODE.slice(position + 1);
          expect(isValidUnitCode(wrong), wrong).toBe(false);
        }
      }
    }
  });

  it("reads typed codes with separators, lower case and look-alikes", () => {
    expect(normalizeUnitCode("7kq2-x9f4 mz")).toBe(CODE);
    expect(normalizeUnitCode("oil")).toBe("011");
    expect(formatUnitCode(CODE)).toBe("7KQ2 X9F4 MZ");
  });

  it("checks EAN-13", () => {
    expect(isValidEan13("2000000000015")).toBe(true);
    expect(isValidEan13("2000000000016")).toBe(false);
    expect(isValidEan13("200000000001")).toBe(false);
  });
});

describe("interpretations", () => {
  it("reads what the scanners deliver", () => {
    expect(interpretations(CODE)).toEqual([{ kind: "unit", code: CODE }]);
    expect(interpretations(" r02-f04-b12 ")).toEqual([{ kind: "location", code: "R02-F04-B12" }]);
    expect(interpretations("2000000000015")).toEqual([{ kind: "variant", code: "2000000000015" }]);
    expect(interpretations("LAGER")).toEqual([{ kind: "location", code: "LAGER" }]);
  });

  it("still understands label URLs", () => {
    expect(interpretations(`https://shop.example/u/${CODE.toLowerCase()}`)).toEqual([
      { kind: "unit", code: CODE },
    ]);
    expect(interpretations("/l/r01")).toEqual([{ kind: "location", code: "R01" }]);
    expect(interpretations("https://shop.example/produkte/x")).toEqual([]);
    expect(interpretations(`https://shop.example/u/${CODE.slice(0, 9)}X`)).toEqual([]);
  });

  it("offers both readings for a code typed like a grouped unit code", () => {
    expect(interpretations("7KQ2-X9F4-MZ")).toEqual([
      { kind: "unit", code: CODE },
      { kind: "location", code: "7KQ2-X9F4-MZ" },
    ]);
  });

  it.each(["", "   ", "Hallo Welt", "R02_F04", "x".repeat(301)])("refuses %j", (raw) => {
    expect(interpretations(raw)).toEqual([]);
  });
});
