import { describe, expect, it } from "vitest";

import type { ProductOut, VariantOut } from "@/lib/api/generated/model";

import { entryPlan, productColors, variantOf } from "./quick-entry";

function variant(finish: string, color: string, sku: string): VariantOut {
  return {
    id: sku,
    finish_code: finish,
    color,
    sku,
    gtin: "",
    price_cents: 6500,
    compare_at_price_cents: null,
    active: true,
    allow_backorder: false,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
  };
}

const PUMA = {
  scales: [
    {
      id: "s1",
      scale_code: "H0",
      length_mm: null,
      width_mm: null,
      height_mm: null,
      weight_g: null,
      variants: [variant("painted", "Grün", "MB-000005-H0-F"), variant("painted", "Blau", "MB-000005-H0-F2")],
    },
  ],
} as unknown as ProductOut;

describe("entryPlan", () => {
  it("knows a new product, a new variant, a new scale and a variant that exists", () => {
    expect(entryPlan(null, { scaleCode: "H0", finishCode: "painted", color: "" })).toEqual({ kind: "new-product" });
    expect(entryPlan(PUMA, { scaleCode: "H0", finishCode: "painted", color: "Grau" })).toEqual({
      kind: "new-variant",
      newScale: false,
    });
    expect(entryPlan(PUMA, { scaleCode: "TT", finishCode: "unpainted", color: "" })).toEqual({
      kind: "new-variant",
      newScale: true,
    });
    const blue = entryPlan(PUMA, { scaleCode: "H0", finishCode: "painted", color: "blau" });
    expect(blue.kind === "existing" && blue.variant.sku).toBe("MB-000005-H0-F2");
  });

  it("lists the product's colours once, in alphabetical order", () => {
    expect(productColors(PUMA)).toEqual(["Blau", "Grün"]);
    expect(productColors(null)).toEqual([]);
    expect(variantOf(PUMA, { scaleCode: "H0", finishCode: "unpainted", color: "" })).toBeUndefined();
  });
});
