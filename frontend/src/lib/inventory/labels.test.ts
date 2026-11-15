import { describe, expect, it } from "vitest";

import type { ScanOut, ScanStockEffectOut } from "@/lib/api/generated/model";

import { scanHeadline } from "./labels";

const LOCATION = {
  code: "R01-F01",
  name: "",
  kind: "compartment",
  holds_goods: true,
  unit_count: 9,
  part_count: 0,
} as const;

function answer(change: Partial<ScanOut>): ScanOut {
  return {
    scan_id: "s1",
    mode: "put_away",
    quantity: 1,
    outcome: "applied",
    message: "booked_in",
    resolved: { kind: "variant", code: "2000000000428" },
    unit: null,
    location: null,
    variant: { variant_id: "v1", title: "Stellwerk Altenau · H0 · bemalt", sku: "MB-000006-H0-B", free_units: 5, free_here: 2 },
    part: null,
    effect: null,
    part_effect: null,
    stock_effect: null,
    progress: null,
    next_expected: null,
    undoable: true,
    undone: false,
    ...change,
  };
}

function booking(change: Partial<ScanStockEffectOut>): ScanStockEffectOut {
  return {
    quantity: 7,
    location: "R01-F01",
    in_location: 9,
    stored: 2,
    created: 5,
    reserved: 0,
    reserved_for: [],
    reason: null,
    from_locations: [],
    ...change,
  };
}

describe("scanHeadline for model labels", () => {
  it("says how many pieces went in and how many lie there now", () => {
    expect(scanHeadline(answer({ stock_effect: booking({}) }))).toBe("+7 · jetzt 9 hier");
    expect(scanHeadline(answer({ stock_effect: booking({ reserved: 2 }) }))).toBe("+7 · jetzt 9 hier · 2 gleich reserviert");
    expect(scanHeadline(answer({ stock_effect: booking({}), undone: true }))).toBe("Rückgängig gemacht.");
  });

  it("says how many went out, why, and what is left", () => {
    const out = { mode: "scrap", message: "booked_out" } as const;
    expect(scanHeadline(answer({ ...out, stock_effect: booking({ quantity: 3, in_location: 2, reason: "sold" }) }))).toBe(
      "−3 · Verkauft · noch 2 hier",
    );
    expect(
      scanHeadline(answer({ ...out, stock_effect: booking({ quantity: 1, location: null, in_location: null, reason: "mistake" }) })),
    ).toBe("−1 · Versehen · noch 5 frei");
  });

  it("says how many are free when too few are, in the place if one is chosen", () => {
    const refused = { mode: "scrap", outcome: "rejected", message: "not_enough_free", quantity: 3 } as const;
    expect(scanHeadline(answer({ ...refused, location: LOCATION }))).toBe("Nur 2 frei in R01-F01, 3 verlangt. Nichts ausgebucht.");
    expect(scanHeadline(answer(refused))).toBe("Nur 5 frei, 3 verlangt. Nichts ausgebucht.");
    const none = answer({ ...refused, location: LOCATION });
    expect(scanHeadline({ ...none, variant: none.variant && { ...none.variant, free_here: 0 } })).toBe(
      "Kein freies Stück in R01-F01. Nichts ausgebucht.",
    );
  });
});
