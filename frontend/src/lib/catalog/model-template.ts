import type { FinishOut, ProductOut } from "@/lib/api/generated/model";

import { centsToEuroInput } from "./format";

/** What the wizard's step 2 asks per finish: chosen or not, its price, and (if painted) its colours. */
export type FinishChoice = { chosen: boolean; price: string; colors: string[]; draft: string };

export type ModelTemplate = {
  categoryId: string;
  scaleCode: string;
  choices: Record<string, FinishChoice>;
};

/**
 * „Wie ein vorhandenes Modell“: a new model usually comes like the last one, in the same
 * scale, finishes, colours and prices, only with another name and other photos. This
 * reads those from an existing model, so the wizard's steps start filled in. The scale
 * is the model's first one that has an Ausführung; finishes no longer offered are left out.
 */
export function templateFrom(product: ProductOut, finishes: readonly FinishOut[]): ModelTemplate {
  const scale = product.scales.find((entry) => entry.variants.some((variant) => variant.active)) ?? product.scales[0];
  const choices: Record<string, FinishChoice> = {};
  for (const variant of scale?.variants.filter((entry) => entry.active) ?? []) {
    const finish = finishes.find((entry) => entry.code === variant.finish_code);
    if (!finish) {
      continue;
    }
    const before = choices[finish.code];
    const colors = before?.colors ?? [];
    const color = variant.color.trim();
    choices[finish.code] = {
      chosen: true,
      // The first price met stays; Ausführungen of one finish usually share it.
      price: before?.price ?? centsToEuroInput(variant.price_cents),
      colors: finish.colored && color !== "" && !colors.includes(color) ? [...colors, color] : colors,
      draft: "",
    };
  }
  return { categoryId: product.primary_category_id ?? "", scaleCode: scale?.scale_code ?? "", choices };
}
