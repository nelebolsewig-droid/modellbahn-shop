import type { ProductOut, VariantOut } from "@/lib/api/generated/model";

import { sameColor } from "./colors";

/*
 * What the quick entry will do with the model on the bench, worked out before the
 * request, so the phone can say it on the button's doorstep: a new product, a new
 * variant, or a variant that exists and gets a new price. The backend decides the same
 * way (CatalogService.quick_entry).
 */

export type EntryChoice = { scaleCode: string; finishCode: string; color: string };

export type EntryPlan =
  | { kind: "new-product" }
  | { kind: "new-variant"; newScale: boolean }
  | { kind: "existing"; variant: VariantOut }
  /** The one variant of the finish has no colour yet: this entry names it. */
  | { kind: "names"; variant: VariantOut }
  /** The finish comes in named colours here: one more needs a name too. */
  | { kind: "needs-color" };

/** The variant of the product in this scale, finish and colour, if there is one. */
export function variantOf(product: ProductOut, choice: EntryChoice): VariantOut | undefined {
  return product.scales
    .find((scale) => scale.scale_code === choice.scaleCode)
    ?.variants.find((variant) => variant.finish_code === choice.finishCode && sameColor(variant.color, choice.color));
}

export function entryPlan(product: ProductOut | null, choice: EntryChoice): EntryPlan {
  if (product === null) {
    return { kind: "new-product" };
  }
  const variant = variantOf(product, choice);
  if (variant) {
    return { kind: "existing", variant };
  }
  const scale = product.scales.find((s) => s.scale_code === choice.scaleCode);
  const siblings = scale?.variants.filter((v) => v.finish_code === choice.finishCode) ?? [];
  const [only] = siblings;
  if (choice.color !== "" && siblings.length === 1 && only && only.color === "") {
    return { kind: "names", variant: only };
  }
  if (choice.color === "" && siblings.length > 0) {
    return { kind: "needs-color" };
  }
  return { kind: "new-variant", newScale: scale === undefined };
}

/** The colours the product already comes in, for one tap; in the order of the alphabet. */
export function productColors(product: ProductOut | null): string[] {
  const all = product?.scales.flatMap((scale) => scale.variants.map((variant) => variant.color)) ?? [];
  return [...new Set(all.filter((color) => color !== ""))].sort((a, b) => a.localeCompare(b, "de"));
}
