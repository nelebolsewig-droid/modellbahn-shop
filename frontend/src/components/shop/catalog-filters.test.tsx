import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CategoryOut } from "@/lib/api/generated/model";

import { CatalogFilters, CatalogSort, categoryTrail, sortFor } from "./catalog-filters";

function category(id: string, name: string, parent: string | null, position = 0): CategoryOut {
  return { id, slug: name.toLowerCase(), name, parent_id: parent, position };
}

const CATEGORIES: CategoryOut[] = [
  category("1", "Gebaeude", null, 0),
  category("2", "Stellwerke", "1", 0),
  category("3", "Bahnbetriebswerk", "1", 1),
  category("4", "Signale", null, 1),
];
const SCALES = [{ code: "H0", name: "H0", ratio: "1:87", track_gauge_mm: 16.5 }];

function categoryNav(kategorie?: string) {
  render(<CatalogFilters query={{ kategorie }} scales={SCALES} categories={CATEGORIES} />);
  return screen.getByRole("navigation", { name: "Kategorie" });
}

describe("categoryTrail", () => {
  it("lists the chosen category with its ancestors, top level first", () => {
    expect(categoryTrail(CATEGORIES, "bahnbetriebswerk").map((c) => c.name)).toEqual(["Gebaeude", "Bahnbetriebswerk"]);
  });

  it("is empty for no or an unknown category", () => {
    expect(categoryTrail(CATEGORIES, undefined)).toEqual([]);
    expect(categoryTrail(CATEGORIES, "gibt-es-nicht")).toEqual([]);
  });

  it("ends on a cycle instead of looping", () => {
    const cycle = [category("a", "A", "b"), category("b", "B", "a")];
    expect(categoryTrail(cycle, "a").map((c) => c.name)).toEqual(["B", "A"]);
  });
});

describe("CatalogFilters", () => {
  it("offers only the top level while no category is chosen", () => {
    const nav = categoryNav();
    expect(within(nav).getByRole("link", { name: "Alle" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).queryByRole("list", { name: /Unterkategorien/ })).toBeNull();
  });

  it("shows the subcategories of a chosen category", () => {
    const nav = categoryNav("gebaeude");
    const sub = within(nav).getByRole("list", { name: "Unterkategorien von Gebaeude" });
    expect(within(sub).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Alle",
      "Stellwerke",
      "Bahnbetriebswerk",
    ]);
    expect(within(sub).getByRole("link", { name: "Alles in Gebaeude" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Gebaeude" })).toHaveAttribute("aria-current", "page");
  });

  it("marks a chosen subcategory and keeps its parent drawn as chosen", () => {
    const nav = categoryNav("bahnbetriebswerk");
    const parent = within(nav).getByRole("link", { name: "Gebaeude" });
    expect(parent).not.toHaveAttribute("aria-current");
    expect(parent.className).toContain("bg-selected");
    const sub = within(nav).getByRole("list", { name: "Unterkategorien von Gebaeude" });
    expect(within(sub).getByRole("link", { name: "Bahnbetriebswerk" })).toHaveAttribute("aria-current", "page");
    expect(within(sub).getByRole("link", { name: "Alles in Gebaeude" })).not.toHaveAttribute("aria-current");
    expect(within(nav).getByRole("link", { name: "Alle" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the gauge when changing the category", () => {
    render(<CatalogFilters query={{ spur: "H0" }} scales={SCALES} categories={CATEGORIES} />);
    const nav = screen.getByRole("navigation", { name: "Kategorie" });
    expect(within(nav).getByRole("link", { name: "Signale" })).toHaveAttribute("href", "/katalog?spur=H0&kategorie=signale");
  });
});

describe("epochs and sorting", () => {
  const EPOCHS = [
    { code: "III", name: "Epoche III", period: "1949–1970" },
    { code: "IV", name: "Epoche IV", period: "1970–1990" },
  ];

  it("keeps the other filters when choosing an epoch", () => {
    render(<CatalogFilters query={{ spur: "H0", sortierung: "name" }} scales={SCALES} categories={[]} epochs={EPOCHS} />);
    const nav = screen.getByRole("navigation", { name: "Epoche" });
    expect(within(nav).getByRole("link", { name: "Epoche III, 1949–1970" })).toHaveAttribute(
      "href",
      "/katalog?spur=H0&epoche=III&sortierung=name",
    );
    expect(within(nav).getByRole("link", { name: "Alle" })).toHaveAttribute("aria-current", "page");
  });

  it("maps the German sort parameter to the API's order", () => {
    expect(sortFor(undefined)).toBe("newest");
    expect(sortFor("preis-auf")).toBe("price_asc");
    expect(sortFor("preis-ab")).toBe("price_desc");
    expect(sortFor("name")).toBe("name");
    expect(sortFor("billig")).toBe("newest");
  });

  it("starts on the first page again when the order changes", () => {
    render(<CatalogSort query={{ epoche: "IV", sortierung: "preis-ab" }} />);
    const nav = screen.getByRole("navigation", { name: "Sortierung" });
    expect(within(nav).getByRole("link", { name: "Preis absteigend" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Neueste" })).toHaveAttribute("href", "/katalog?epoche=IV");
    expect(within(nav).getByRole("link", { name: "Name" })).toHaveAttribute("href", "/katalog?epoche=IV&sortierung=name");
  });
});
