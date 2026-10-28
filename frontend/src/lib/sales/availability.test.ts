import { describe, expect, it } from "vitest";

import type { VariantAvailabilityOut } from "@/lib/api/generated/model";
import { cartLine } from "@/test/sales";

import { availabilityFor, availabilityNote, cartLeadTime, leadTimeText, orderableMax } from "./availability";

function info(free: number, lead: [number, number] | null = null): VariantAvailabilityOut {
  return {
    variant_id: "v1",
    availability: free > 0 ? "in_stock" : lead ? "made_to_order" : "unavailable",
    free_units: free,
    lead_time_min_weeks: lead?.[0] ?? null,
    lead_time_max_weeks: lead?.[1] ?? null,
  };
}

describe("availability in the shop", () => {
  it("writes lead times the German way", () => {
    expect(leadTimeText([4, 6])).toBe("4–6 Wochen");
    expect(leadTimeText([3, 3])).toBe("3 Wochen");
    expect(leadTimeText([1, 1])).toBe("1 Woche");
  });

  it("ships from the shelf while enough lie there, builds to order beyond that", () => {
    expect(availabilityFor(info(2, [4, 6]), 2)).toBe("in_stock");
    expect(availabilityFor(info(2, [4, 6]), 3)).toBe("made_to_order");
    expect(availabilityFor(info(2), 3)).toBe("unavailable");
  });

  it("limits the quantity by the shelf only for stock articles", () => {
    expect(orderableMax(info(2))).toBe(2);
    expect(orderableMax(info(0, [4, 6]))).toBe(99);
    expect(orderableMax(undefined)).toBe(99);
  });

  it("names the state with an honest hint", () => {
    expect(availabilityNote("in_stock", 2, info(2))).toEqual({ label: "Sofort lieferbar", tone: "success", detail: "Nur noch 2 Stück" });
    expect(availabilityNote("in_stock", 12, info(12)).detail).toBeNull();
    expect(availabilityNote("made_to_order", 0, info(0, [4, 6]))).toEqual({
      label: "Wird für dich gefertigt",
      tone: "accent",
      detail: "Lieferzeit 4–6 Wochen",
    });
    expect(availabilityNote("unavailable", 0, info(0)).label).toBe("Derzeit nicht lieferbar");
  });

  it("takes the longest lead time of the built-to-order lines", () => {
    const lines = [
      cartLine({ variant_id: "a", availability: "in_stock" }),
      cartLine({ variant_id: "b", availability: "made_to_order", lead_time_min_weeks: 4, lead_time_max_weeks: 6 }),
      cartLine({ variant_id: "c", availability: "made_to_order", lead_time_min_weeks: 2, lead_time_max_weeks: 8 }),
    ];
    expect(cartLeadTime(lines)).toEqual([4, 8]);
    expect(cartLeadTime([cartLine()])).toBeNull();
  });
});
