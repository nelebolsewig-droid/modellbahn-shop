/*
 * Whether a variant can be delivered, in the shop's words. Mirrors the backend
 * (inventory/domain/availability.py): enough free pieces on the shelf ship at once;
 * beyond them the workshop makes more within the lead time (every model, unless it is a
 * one-off, ADR 0029); anything else cannot be ordered right now. The words say how many
 * ship at once and that the rest is made, never that the whole line is.
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

/** The day by which a lead time counted from ``from`` runs out (its longer end). */
export function readyBy(from: string, [, max]: LeadTime): Date {
  const date = new Date(from);
  date.setDate(date.getDate() + max * 7);
  return date;
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

/** Up to this many pieces on the shelf, the shop says how few are left. */
const FEW = 3;

/**
 * Badge text and tone for a variant on its page, plus a quieter second line: "Nur noch
 * 3 Stück sofort lieferbar – weitere fertigen wir für dich (Lieferzeit 2–4 Wochen)" when
 * the shelf runs short of a model that is made again.
 */
export function availabilityNote(
  availability: Availability,
  freeUnits: number,
  leadTime: { lead_time_min_weeks: number | null; lead_time_max_weeks: number | null },
): AvailabilityNote {
  const weeks = leadTimeOf(leadTime.lead_time_min_weeks, leadTime.lead_time_max_weeks);
  const few = freeUnits > 0 && freeUnits <= FEW;
  if (weeks !== null && availability !== "unavailable" && freeUnits > 0 && (few || availability === "made_to_order")) {
    return {
      label: `Nur noch ${freeUnits} Stück sofort lieferbar`,
      tone: availability === "in_stock" ? "success" : "accent",
      detail: `– weitere fertigen wir für dich (Lieferzeit ${leadTimeText(weeks)})`,
    };
  }
  if (availability === "in_stock") {
    return {
      label: "Sofort lieferbar",
      tone: "success",
      // Honest scarcity: only shown when it is really just a few.
      detail: few ? `Nur noch ${freeUnits} Stück` : null,
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

/**
 * A cart line in the shop's words: "Sofort lieferbar", "3 sofort lieferbar, 2 werden für
 * dich gefertigt · Lieferzeit 2–4 Wochen", or "Wird für dich gefertigt · Lieferzeit …".
 */
export function cartLineNote(line: CartLineOut): AvailabilityNote {
  const weeks = leadTimeOf(line.lead_time_min_weeks, line.lead_time_max_weeks);
  if (line.availability === "in_stock") {
    return { label: "Sofort lieferbar", tone: "success", detail: null };
  }
  if (line.availability === "unavailable") {
    return availabilityNote(line.availability, line.free_units, line);
  }
  const detail = weeks ? `Lieferzeit ${leadTimeText(weeks)}` : null;
  const fromShelf = Math.min(line.free_units, line.quantity);
  if (fromShelf <= 0) {
    return { label: "Wird für dich gefertigt", tone: "accent", detail };
  }
  const made = line.quantity - fromShelf;
  return {
    label: `${fromShelf} sofort lieferbar, ${made} ${made === 1 ? "wird" : "werden"} für dich gefertigt`,
    tone: "accent",
    detail,
  };
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
