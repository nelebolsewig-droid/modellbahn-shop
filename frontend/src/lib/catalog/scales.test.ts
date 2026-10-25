import { describe, expect, it } from "vitest";

import type { NavigationCategoryOut } from "@/lib/api/generated/model";

import {
  branchCount,
  busiestScale,
  catalogPath,
  findScale,
  millimetresPerMetre,
  scaleLabel,
} from "./scales";

function category(id: string, parent: string | null, counts: Record<string, number> = {}): NavigationCategoryOut {
  return { id, parent_id: parent, slug: id, name: id, position: 0, product_counts: counts };
}

// Straßenfahrzeuge > LKW > Feuerwehr, and Schienenfahrzeuge beside them.
const TREE = [
  category("strasse", null),
  category("lkw", "strasse", { H0: 2 }),
  category("feuerwehr", "lkw", { H0: 1, "124": 3 }),
  category("schiene", null, { N: 4 }),
];

describe("scaleLabel", () => {
  it("names the scale and its ratio", () => {
    expect(scaleLabel({ code: "H0", name: "H0", ratio: "1:87" })).toBe("H0 · 1:87");
  });

  it("does not repeat a ratio that is the name", () => {
    expect(scaleLabel({ code: "124", name: "1:24", ratio: "1:24" })).toBe("1:24");
  });
});

describe("addresses", () => {
  it("puts scale and category into the path and the filters into the query", () => {
    expect(catalogPath({ scale: "H0" })).toBe("/katalog/h0");
    expect(catalogPath({ scale: "H0", category: "lkw", sortierung: "name", epoche: "III" })).toBe(
      "/katalog/h0/lkw?epoche=III&sortierung=name",
    );
  });

  it("finds the scale of an address regardless of case", () => {
    const scales = [{ code: "H0" }, { code: "124" }];
    expect(findScale(scales, "h0")).toEqual({ code: "H0" });
    expect(findScale(scales, "124")).toEqual({ code: "124" });
    expect(findScale(scales, "x")).toBeUndefined();
  });
});

describe("counting", () => {
  it("adds up a branch in one scale", () => {
    expect(branchCount(TREE, "strasse", "H0")).toBe(3);
    expect(branchCount(TREE, "strasse", "124")).toBe(3);
    expect(branchCount(TREE, "lkw", "N")).toBe(0);
    expect(branchCount(TREE, "schiene", "N")).toBe(4);
  });

  it("survives a cycle in the data", () => {
    const loop = [category("a", "b", { H0: 1 }), category("b", "a", { H0: 1 })];
    expect(branchCount(loop, "a", "H0")).toBe(2);
  });

  it("picks the scale with the most products in a branch", () => {
    const scales = [{ code: "N" }, { code: "H0" }, { code: "124" }];
    expect(busiestScale(scales, TREE, "feuerwehr")).toEqual({ code: "124" });
    expect(busiestScale(scales, TREE, "schiene")).toEqual({ code: "N" });
    expect(busiestScale([{ code: "Z" }], TREE, "strasse")).toBeUndefined();
  });
});

describe("millimetresPerMetre", () => {
  it("is the length of one metre of the original", () => {
    expect(millimetresPerMetre(87)).toBeCloseTo(11.49, 2);
    expect(millimetresPerMetre(22.5)).toBeCloseTo(44.44, 2);
  });
});
