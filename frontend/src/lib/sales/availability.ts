/*
 * Whether a variant can be delivered, in the shop's words. Mirrors the backend
 * (inventory/domain/availability.py): enough free pieces on the shelf ship at once;
 * otherwise a variant made to order is built within its lead time; anything else
 * cannot be ordered right now.
 */

import type { StatusTone } from "@/components/ui/status-badge";
import type { Availability, CartLineOut, VariantAvailabilityOut } from "@/lib/api/generated/model";

export type LeadTime = readonly [min: number, max: number];

/** "4–6 Wochen", "3 Wochen", "1 Woche". */
export function leadTimeText([min, max]: LeadTime): string {
  if (min === max) {
    return min === 1 ? "1 Woche" : `${min} Wochen`;
  }
  return `${min}–${max} Wochen`;
}

function leadTimeOf(min: number | null, max: number | null): LeadTime | null {
  return min === null || max === null ? null : [min, max];
}

/** The answer for `wanted` pieces, from what the availability endpoint says about one. */
export function availabilityFor(info: VariantAvailabilityOut, wanted: number): Availability {
  if (info.free_units >= wanted) {
    return "in_stock";
  }
  return info.lead_time_min_weeks !== null ? "made_to_order" : "unavailable";
}

/** How many of a variant fit in the cart: the shelf limits only what is not made to order. */
export function orderableMax(info: VariantAvailabilityOut | undefined, cap = 99): number {
  if (info === undefined || info.lead_time_min_weeks !== null) {
    return cap;
  }
  return Math.min(cap, info.free_units);
}

export type AvailabilityNote = { label: string; tone: StatusTone; detail: string | null };

/** Badge text and tone for a variant, plus a quieter second line. */
export function availabilityNote(
  availability: Availability,
  freeUnits: number,
  leadTime: { lead_time_min_weeks: number | null; lead_time_max_weeks: number | null },
): AvailabilityNote {
  const weeks = leadTimeOf(leadTime.lead_time_min_weeks, leadTime.lead_time_max_weeks);
  if (availability === "in_stock") {
    return {
      label: "Sofort lieferbar",
      tone: "success",
      // Honest scarcity: only shown when it is really just a few.
      detail: freeUnits > 0 && freeUnits <= 3 ? (freeUnits === 1 ? "Nur noch 1 Stück" : `Nur noch ${freeUnits} Stück`) : null,
    };
  }
  if (availability === "made_to_order") {
    return {
      label: "Wird für dich gefertigt",
      tone: "accent",
      detail: weeks ? `Lieferzeit ${leadTimeText(weeks)}` : null,
    };
  }
  return { label: "Derzeit nicht lieferbar", tone: "neutral", detail: null };
}

/** The longest lead time of the lines that are built to order; null if all ship at once. */
export function cartLeadTime(lines: readonly CartLineOut[]): LeadTime | null {
  let result: LeadTime | null = null;
  for (const line of lines) {
    const weeks = leadTimeOf(line.lead_time_min_weeks, line.lead_time_max_weeks);
    if (line.available && line.availability === "made_to_order" && weeks !== null) {
      result = result === null ? weeks : [Math.max(result[0], weeks[0]), Math.max(result[1], weeks[1])];
    }
  }
  return result;
}
