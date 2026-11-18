import { describe, expect, it } from "vitest";

import { activeSection, barSections, railSections, moreSections } from "./sections";

const labels = (sections: readonly { label: string }[]) => sections.map((section) => section.label);

describe("Stellwerk sections", () => {
  it("shows a packer only what a packer can use", () => {
    expect(labels(railSections("packer"))).toEqual(["Heute", "Bestellungen", "Lager", "Fertigung"]);
    expect(labels(barSections("packer"))).toEqual(["Bestellungen", "Scannen", "Lager"]);
    expect(labels(moreSections("packer"))).toEqual(["Heute", "Fertigung"]);
  });

  it("shows owner and staff the day's work first: Modelle, Bestellungen, Scannen, Lager", () => {
    for (const role of ["owner", "staff"] as const) {
      expect(labels(railSections(role))).toEqual([
        "Heute",
        "Bestellungen",
        "Modelle",
        "Lager",
        "Fertigung",
        "Messen",
        "eBay",
        "Einstellungen",
      ]);
      expect(labels(barSections(role))).toEqual(["Modelle", "Bestellungen", "Scannen", "Lager"]);
      expect(labels(moreSections(role))).toEqual(["Heute", "Fertigung", "Messen", "eBay", "Einstellungen"]);
    }
  });

  it.each([
    ["/admin", "overview"],
    ["/admin/bestellungen/o1", "orders"],
    ["/admin/lager/einheiten/7K3M9QX2TA", "stock"],
    ["/admin/fertigung/drucker/p1", "manufacturing"],
    ["/admin/scanner", "scan"],
    ["/admin/modelle", "models"],
    ["/admin/modelle/p1", "models"],
    ["/admin/modelle/neu", "models"],
    ["/admin/einstellungen/kategorien", "settings"],
    ["/admin/einstellungen/massstaebe", "settings"],
    ["/admin/einstellungen", "settings"],
    ["/admin/einstellungen/ebay", "settings"],
    ["/admin/ebay", "ebay"],
    ["/admin/messen", "fairs"],
    ["/admin/anmelden", null],
  ] as const)("files %s under %s", (pathname, key) => {
    expect(activeSection(pathname)).toBe(key);
  });
});
