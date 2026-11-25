import type { ProductLabel } from "@/lib/api/generated/model";

/*
 * The shop's filters beyond category and epoch: kit or finished model, and the label a
 * model is sold under. German words in the address, the API's codes behind them.
 */

/** Kit or finished model, by the German word in the address and the API's finish code. */
export const FINISH_FILTERS = [
  { param: "bausatz", code: "unpainted", label: "Bausatz" },
  { param: "fertigmodell", code: "painted", label: "Fertigmodell" },
] as const;

/** adp's own models and the partner labels. */
export const LABEL_FILTERS = [
  { param: "adp", label: "adp" },
  { param: "vehicle-world", label: "Vehicle World" },
  { param: "milmod", label: "MilMod" },
] as const satisfies readonly { param: ProductLabel; label: string }[];

/** The finish code for `?ausfuehrung=`; unknown words lift the filter. */
export function finishFor(param: string | undefined): string | undefined {
  return FINISH_FILTERS.find((entry) => entry.param === param)?.code;
}

/** The label for `?label=`; unknown values lift the filter. */
export function labelFor(param: string | undefined): ProductLabel | undefined {
  return LABEL_FILTERS.find((entry) => entry.param === param)?.param;
}

/** How a label is written in the shop, e.g. "Vehicle World". */
export function labelName(label: string): string {
  return LABEL_FILTERS.find((entry) => entry.param === label)?.label ?? label;
}
