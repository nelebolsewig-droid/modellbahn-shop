import { describe, expect, it } from "vitest";

import type { FinishOut, ProductOut, VariantOut } from "@/lib/api/generated/model";

import { templateFrom } from "./model-template";

const finishes = [
  { code: "kit", name: "Bausatz", colored: false, offered: true },
  { code: "painted", name: "Lackiert", colored: true, offered: true },
] as unknown as FinishOut[];

function variant(finish: string, color: string, cents: number, active = true): VariantOut {
  return { id: `${finish}-${color}`, finish_code: finish, color, price_cents: cents, active } as unknown as VariantOut;
}

function product(scales: { scale_code: string; variants: VariantOut[] }[]): ProductOut {
  return { primary_category_id: "cat-1", scales } as unknown as ProductOut;
}

describe("templateFrom", () => {
  it("takes scale, category, finishes, prices and colours of the model", () => {
    const template = templateFrom(
      product([{ scale_code: "H0", variants: [variant("kit", "", 4990), variant("painted", "Rot", 8000), variant("painted", "Blau", 8000)] }]),
      finishes,
    );
    expect(template.categoryId).toBe("cat-1");
    expect(template.scaleCode).toBe("H0");
    expect(template.choices.kit).toEqual({ chosen: true, price: "49,90", colors: [], draft: "" });
    expect(template.choices.painted).toEqual({ chosen: true, price: "80,00", colors: ["Rot", "Blau"], draft: "" });
  });

  it("skips switched-off Ausführungen and finishes no longer offered", () => {
    const template = templateFrom(
      product([{ scale_code: "TT", variants: [variant("kit", "", 3000, false), variant("resin", "", 9000), variant("painted", "Grün", 6000)] }]),
      finishes,
    );
    expect(Object.keys(template.choices)).toEqual(["painted"]);
  });

  it("works for a model without Ausführungen", () => {
    expect(templateFrom(product([]), finishes)).toEqual({ categoryId: "cat-1", scaleCode: "", choices: {} });
  });
});
