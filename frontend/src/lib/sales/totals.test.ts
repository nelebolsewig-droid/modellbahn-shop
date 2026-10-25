import { describe, expect, it } from "vitest";

import { AUSTRIA, GERMANY } from "@/test/sales";

import { includedVat, missingForFreeShipping, shippingCents, totalsFor } from "./totals";

describe("includedVat", () => {
  it.each([
    [11900, 1900],
    [5480, 875], // 874.96 rounds up
    [7, 1], // 1.12 rounds down
    [3, 0],
    [0, 0],
  ])("takes the VAT out of %i cents: %i", (gross, vat) => {
    expect(includedVat(gross)).toBe(vat);
  });
});

describe("shipping", () => {
  it("charges the zone's rate below the threshold and nothing from it on", () => {
    expect(shippingCents(GERMANY, 4999)).toBe(490);
    expect(shippingCents(GERMANY, 5000)).toBe(0);
    expect(shippingCents(AUSTRIA, 9999)).toBe(990);
    expect(shippingCents(AUSTRIA, 10000)).toBe(0);
  });

  it("costs nothing when there is nothing to ship", () => {
    expect(shippingCents(GERMANY, 0)).toBe(0);
    expect(missingForFreeShipping(GERMANY, 0)).toBe(0);
  });

  it("says how much is missing for free shipping", () => {
    expect(missingForFreeShipping(GERMANY, 4990)).toBe(10);
    expect(missingForFreeShipping(GERMANY, 6000)).toBe(0);
    expect(missingForFreeShipping(AUSTRIA, 4990)).toBe(5010);
  });
});

describe("totalsFor", () => {
  it("adds shipping and names the VAT of the whole", () => {
    expect(totalsFor(4990, GERMANY)).toEqual({
      subtotal_cents: 4990,
      shipping_cents: 490,
      total_cents: 5480,
      tax_cents: 875,
    });
  });

  it("changes with the destination", () => {
    expect(totalsFor(7990, GERMANY).total_cents).toBe(7990);
    expect(totalsFor(7990, AUSTRIA).total_cents).toBe(8980);
  });
});
