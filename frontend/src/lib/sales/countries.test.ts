import { describe, expect, it } from "vitest";

import { FRANCE, GERMANY } from "@/test/sales";

import { normalizePostalCode, SHIPPING_COUNTRY_LIST, shippingGroups } from "./countries";

describe("shipping countries", () => {
  it("lists Germany first and every member state of the EU once", () => {
    const codes = SHIPPING_COUNTRY_LIST.map((country) => country.code);
    expect(codes[0]).toBe("DE");
    expect(new Set(codes).size).toBe(27);
  });

  it("accepts each country's own example", () => {
    for (const country of SHIPPING_COUNTRY_LIST) {
      expect(country.postal.test(country.example), country.code).toBe(true);
    }
  });

  it("writes postal codes upper case with single spaces", () => {
    expect(normalizePostalCode("  d02   x285 ")).toBe("D02 X285");
  });

  it("groups countries with the same terms", () => {
    const austria = { ...FRANCE, code: "AT", name: "Österreich" };
    expect(shippingGroups([GERMANY, FRANCE, austria]).map((group) => group.map((c) => c.code))).toEqual([
      ["DE"],
      ["FR", "AT"],
    ]);
  });
});
