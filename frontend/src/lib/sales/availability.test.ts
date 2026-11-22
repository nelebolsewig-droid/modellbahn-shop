import { describe, expect, it } from "vitest";

import type { VariantAvailabilityOut } from "@/lib/api/generated/model";
import { cartLine } from "@/test/sales";

import { availabilityFor, availabilityNote, cartLeadTime, cartLineNote, leadTimeText, orderableMax } from "./availability";

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
      label: "Fertigung nach Bestellung",
      tone: "accent",
      detail: "Lieferzeit 4–6 Wochen",
    });
    expect(availabilityNote("unavailable", 0, info(0)).label).toBe("Derzeit nicht lieferbar");
  });

  it("says how many ship at once when the rest is made, not that all of it is", () => {
    const note = availabilityNote("in_stock", 3, info(3, [2, 4]));
    expect(`${note.label} ${note.detail}`).toBe("Nur noch 3 Stück sofort lieferbar – weitere fertigen wir für dich (Lieferzeit 2–4 Wochen)");
    // More wanted than the shelf holds: the same words.
    expect(availabilityNote("made_to_order", 2, info(2, [2, 4])).label).toBe("Nur noch 2 Stück sofort lieferbar");
    // Plenty on the shelf: no word about making.
    expect(availabilityNote("in_stock", 12, info(12, [2, 4]))).toEqual({ label: "Sofort lieferbar", tone: "success", detail: null });
    // Nothing on the shelf: all of it is made.
    expect(availabilityNote("made_to_order", 0, info(0, [2, 4])).label).toBe("Fertigung nach Bestellung");
  });

  it("splits a cart line into what ships at once and what is made", () => {
    const line = (quantity: number, free: number) =>
      cartLine({ quantity, free_units: free, availability: free >= quantity ? "in_stock" : "made_to_order", lead_time_min_weeks: 2, lead_time_max_weeks: 4 });
    const split = cartLineNote(line(5, 3));
    expect(`${split.label} · ${split.detail}`).toBe("3 sofort lieferbar, 2 in Fertigung nach Bestellung · Lieferzeit 2–4 Wochen");
    expect(cartLineNote(line(4, 3)).label).toBe("3 sofort lieferbar, 1 in Fertigung nach Bestellung");
    expect(cartLineNote(line(2, 0)).label).toBe("Fertigung nach Bestellung");
    expect(cartLineNote(line(2, 5)).label).toBe("Sofort lieferbar");
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
