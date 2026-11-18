import { describe, expect, it } from "vitest";

import { findShortcuts, looksLikeOrderNumber } from "./quick-find";

describe("findShortcuts", () => {
  it("finds pages by their words, umlauts and ß folded", () => {
    expect(findShortcuts("massstabe", "owner")[0]?.href).toBe("/admin/einstellungen/massstaebe");
    expect(findShortcuts("drucker", "owner")[0]?.href).toBe("/admin/fertigung");
    expect(findShortcuts("neu modell", "owner")[0]?.href).toBe("/admin/modelle/neu");
  });

  it("leaves office pages out for packers", () => {
    expect(findShortcuts("modell", "packer").map((entry) => entry.href)).not.toContain("/admin/modelle");
    expect(findShortcuts("", "packer").every((entry) => !entry.officeOnly)).toBe(true);
  });
});

describe("looksLikeOrderNumber", () => {
  it("tells numbers from names", () => {
    expect(looksLikeOrderNumber("MB-2026-00012")).toBe(true);
    expect(looksLikeOrderNumber("00012")).toBe(true);
    expect(looksLikeOrderNumber("Kipper")).toBe(false);
  });
});
