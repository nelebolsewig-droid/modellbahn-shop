import { describe, expect, it } from "vitest";

import type { ShippingCountryOut } from "@/lib/api/generated/model";
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

/** A zone that ships free from 50 €, as the backend still allows. */
const WITH_THRESHOLD: ShippingCountryOut = { ...GERMANY, rate_cents: 490, free_from_cents: 5000 };

describe("shipping", () => {
  it("charges the flat rate however much is ordered", () => {
    expect(shippingCents(GERMANY, 4999)).toBe(590);
    expect(shippingCents(GERMANY, 500000)).toBe(590);
    expect(shippingCents(AUSTRIA, 9999)).toBe(1690);
  });

  it("ships free from a zone's threshold where there is one", () => {
    expect(shippingCents(WITH_THRESHOLD, 4999)).toBe(490);
    expect(shippingCents(WITH_THRESHOLD, 5000)).toBe(0);
  });

  it("costs nothing when there is nothing to ship", () => {
    expect(shippingCents(GERMANY, 0)).toBe(0);
    expect(missingForFreeShipping(WITH_THRESHOLD, 0)).toBe(0);
  });

  it("says how much is missing for free shipping, and nothing where it is never free", () => {
    expect(missingForFreeShipping(WITH_THRESHOLD, 4990)).toBe(10);
    expect(missingForFreeShipping(WITH_THRESHOLD, 6000)).toBe(0);
    expect(missingForFreeShipping(GERMANY, 4990)).toBeNull();
  });
});

describe("totalsFor", () => {
  it("adds shipping and names the VAT of the whole", () => {
    expect(totalsFor(4990, GERMANY)).toEqual({
      subtotal_cents: 4990,
      shipping_cents: 590,
      total_cents: 5580,
      tax_cents: 891,
    });
  });

  it("changes with the destination", () => {
    expect(totalsFor(7990, GERMANY).total_cents).toBe(8580);
    expect(totalsFor(7990, AUSTRIA).total_cents).toBe(9680);
  });
});
