import { describe, expect, it } from "vitest";

import { activeSection, barSections, headerSections, moreSections } from "./sections";

const labels = (sections: readonly { label: string }[]) => sections.map((section) => section.label);

describe("Stellwerk sections", () => {
  it("shows a packer only what a packer can use", () => {
    expect(labels(headerSections("packer"))).toEqual(["Übersicht", "Bestellungen", "Lager", "Fertigung"]);
    expect(labels(barSections("packer"))).toEqual(["Übersicht", "Bestellungen", "Scannen", "Lager"]);
    expect(labels(moreSections("packer"))).toEqual(["Fertigung"]);
  });

  it("shows owner and staff everything, the day's work first and the settings last", () => {
    for (const role of ["owner", "staff"] as const) {
      expect(labels(headerSections(role))).toEqual([
        "Übersicht",
        "Bestellungen",
        "Lager",
        "Fertigung",
        "Katalog",
        "Messen",
        "eBay",
        "Einstellungen",
      ]);
      expect(labels(moreSections(role))).toEqual([
        "Fertigung",
        "Katalog",
        "Neues Modell",
        "Messen",
        "eBay",
        "Einstellungen",
      ]);
    }
  });

  it.each([
    ["/admin", "overview"],
    ["/admin/bestellungen/o1", "orders"],
    ["/admin/lager/einheiten/7K3M9QX2TA", "stock"],
    ["/admin/fertigung/drucker/p1", "manufacturing"],
    ["/admin/scanner", "scan"],
    ["/admin/katalog", "catalog"],
    ["/admin/katalog/p1", "catalog"],
    ["/admin/erfassen", "newModel"],
    ["/admin/katalog/kategorien", "settings"],
    ["/admin/katalog/massstaebe", "settings"],
    ["/admin/einstellungen", "settings"],
    ["/admin/einstellungen/ebay", "settings"],
    ["/admin/ebay", "ebay"],
    ["/admin/messen", "fairs"],
    ["/admin/anmelden", null],
  ] as const)("files %s under %s", (pathname, key) => {
    expect(activeSection(pathname)).toBe(key);
  });
});
