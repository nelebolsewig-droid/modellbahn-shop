import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { NavigationCategoryOut, NavigationScaleOut } from "@/lib/api/generated/model";

import { CatalogSort, CategoryTree, EpochFilter, ScaleSwitch, categoryTrail, sortFor } from "./catalog-nav";

function category(
  id: string,
  name: string,
  parent: string | null,
  counts: Record<string, number> = {},
  position = 0,
): NavigationCategoryOut {
  return { id, slug: id, name, parent_id: parent, position, product_counts: counts };
}

// Schienenfahrzeuge (Eisenbahn, Straßenbahn) and Straßenfahrzeuge (LKW > Feuerwehr, PKW).
const CATEGORIES = [
  category("schiene", "Schienenfahrzeuge", null, {}, 0),
  category("eisenbahn", "Eisenbahn", "schiene", { H0: 3, N: 1 }),
  category("strassenbahn", "Straßenbahn", "schiene", { N: 2 }),
  category("strasse", "Straßenfahrzeuge", null, {}, 1),
  category("lkw", "LKW", "strasse", { H0: 1 }),
  category("feuerwehr", "Feuerwehr", "lkw", { H0: 2, "124": 1 }),
  category("pkw", "PKW", "strasse"),
];

function scale(code: string, name: string, ratio: string, count: number): NavigationScaleOut {
  return { code, name, ratio, ratio_denominator: Number(ratio.split(":")[1]), track_gauge_mm: null, product_count: count };
}

const SCALES = [scale("N", "N", "1:160", 3), scale("H0", "H0", "1:87", 6), scale("124", "1:24", "1:24", 1), scale("Z", "Z", "1:220", 0)];

function tree(location: Parameters<typeof CategoryTree>[0]["location"]) {
  render(<CategoryTree location={location} categories={CATEGORIES} />);
  return screen.getByRole("navigation", { name: "Kategorie" });
}

describe("CategoryTree", () => {
  it("offers only categories with models in the scale, with the counts of their branch", () => {
    const nav = tree({ scale: "H0" });
    const links = within(nav).getAllByRole("link").map((link) => link.textContent);
    expect(links).toEqual(["Alle Kategorien6", "Schienenfahrzeuge3", "Straßenfahrzeuge3"]);
    expect(within(nav).getByRole("link", { name: /Alle Kategorien/ })).toHaveAttribute("aria-current", "page");
  });

  it("opens the chosen branch down to the chosen category", () => {
    const nav = tree({ scale: "H0", category: "lkw", sortierung: "name" });
    expect(within(nav).getByRole("link", { name: /^LKW/ })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: /^Feuerwehr/ })).toHaveAttribute("href", "/katalog/h0/feuerwehr?sortierung=name");
    // PKW has no models in H0, Straßenbahn none in H0, and Eisenbahn's branch is closed.
    expect(within(nav).queryByRole("link", { name: /PKW/ })).toBeNull();
    expect(within(nav).queryByRole("link", { name: /Eisenbahn|Straßenbahn/ })).toBeNull();
  });

  it("finds the way up from a subcategory", () => {
    expect(categoryTrail(CATEGORIES, "feuerwehr").map((c) => c.name)).toEqual(["Straßenfahrzeuge", "LKW", "Feuerwehr"]);
    expect(categoryTrail(CATEGORIES, undefined)).toEqual([]);
  });
});

describe("ScaleSwitch", () => {
  it("keeps the category where the other scale has models in it", () => {
    render(<ScaleSwitch location={{ scale: "H0", category: "feuerwehr" }} scales={SCALES} categories={CATEGORIES} />);
    const nav = screen.getByRole("navigation", { name: "Maßstab wechseln" });
    expect(within(nav).getByRole("link", { name: "Maßstab 1:24" })).toHaveAttribute("href", "/katalog/124/feuerwehr");
    expect(within(nav).getByRole("link", { name: "Maßstab N · 1:160" })).toHaveAttribute("href", "/katalog/n");
    expect(within(nav).getByRole("link", { name: "Maßstab H0 · 1:87" })).toHaveAttribute("aria-current", "page");
    // Z has no models yet and is not offered.
    expect(within(nav).getAllByRole("link")).toHaveLength(3);
  });
});

describe("epochs and order", () => {
  it("keeps the other filters when choosing an epoch", () => {
    render(
      <EpochFilter
        location={{ scale: "H0", category: "lkw", sortierung: "name", weiter: "abc" }}
        epochs={[{ code: "III", name: "Epoche III", period: "1949–1970" }]}
      />,
    );
    expect(screen.getByRole("link", { name: "Epoche III, 1949–1970" })).toHaveAttribute(
      "href",
      "/katalog/h0/lkw?epoche=III&sortierung=name",
    );
  });

  it("maps the German sort parameter to the API's order", () => {
    expect(sortFor(undefined)).toBe("newest");
    expect(sortFor("preis-auf")).toBe("price_asc");
    expect(sortFor("preis-ab")).toBe("price_desc");
    expect(sortFor("billig")).toBe("newest");
  });

  it("starts on the first page again when the order changes", () => {
    render(<CatalogSort location={{ scale: "N", epoche: "IV", sortierung: "preis-ab", weiter: "abc" }} />);
    const nav = screen.getByRole("navigation", { name: "Sortierung" });
    expect(within(nav).getByRole("link", { name: "Preis absteigend" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Neueste" })).toHaveAttribute("href", "/katalog/n?epoche=IV");
  });
});
