/*
 * The shop's lead time for pieces made again (ADR 0029): one for every variant that has
 * none of its own. Owner and staff read it; only the owner changes it (Einstellungen).
 */

import { useGetProduction } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { VariantOut } from "@/lib/api/generated/model";
import type { LeadTime } from "@/lib/sales/availability";

/** What the migration starts with; shown until the real value has loaded. */
export const INITIAL_LEAD_TIME: LeadTime = [2, 4];

/** The shop's lead time, or null while it loads (or cannot be read). */
export function useShopLeadTime(): LeadTime | null {
  const production = useGetProduction({
    query: {
      staleTime: 60_000,
      select: (data): LeadTime => [data.default_lead_time_min_weeks, data.default_lead_time_max_weeks],
    },
  });
  return production.data ?? null;
}

/** How a variant is made again: in the shop's lead time, in its own, or not at all. */
export type MadeAgain = "standard" | "own" | "none";

export function madeAgain(variant: Pick<VariantOut, "allow_backorder" | "lead_time_min_weeks">): MadeAgain {
  if (!variant.allow_backorder) {
    return "none";
  }
  return variant.lead_time_min_weeks === null ? "standard" : "own";
}
