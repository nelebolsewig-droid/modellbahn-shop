import { describe, expect, it } from "vitest";

import type { GalleryItemOut } from "@/lib/api/generated/model";

import { colorsWithoutPhoto, mergeDraft } from "./product-gallery";

function item(id: string): GalleryItemOut {
  return { asset_id: id, position: 0, role: "gallery", alt_text: "", scale_code: null, finish_code: null, color: null, image: null };
}

describe("mergeDraft", () => {
  it("keeps local order and texts, drops what is gone and appends what is new", () => {
    const draft = [
      { asset_id: "b", alt_text: "Rückseite" },
      { asset_id: "gone", alt_text: "" },
      { asset_id: "a", alt_text: "Front" },
    ];
    const merged = mergeDraft(draft, [item("a"), item("b"), item("new")]);
    expect(merged.map((entry) => [entry.asset_id, entry.alt_text])).toEqual([
      ["b", "Rückseite"],
      ["a", "Front"],
      ["new", ""],
    ]);
  });
});

describe("colorsWithoutPhoto", () => {
  const entry = (color: string | null) => ({ asset_id: crypto.randomUUID(), color });

  it("names the colours no photo shows yet", () => {
    expect(colorsWithoutPhoto(["Blau", "Rot", "Grün"], [entry("Blau"), entry(null), entry("rot")])).toEqual(["Grün"]);
  });

  it("asks nothing of a model in one colour", () => {
    expect(colorsWithoutPhoto(["Blau"], [entry(null)])).toEqual([]);
    expect(colorsWithoutPhoto([], [entry(null)])).toEqual([]);
  });
});
