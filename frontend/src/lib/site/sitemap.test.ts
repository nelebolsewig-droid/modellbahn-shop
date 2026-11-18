import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NavigationCategoryOut, NavigationOut } from "@/lib/api/generated/model";
import { ApiProblem } from "@/lib/api/problem";
import { fetchStore } from "@/lib/api/server";

import { catalogPaths, SITEMAP_PAGES, sitemapEntries } from "./sitemap";

vi.mock("@/lib/api/server", () => ({ fetchStore: vi.fn() }));

const fetchStoreMock = vi.mocked(fetchStore);

function category(id: string, parent: string | null, counts: Record<string, number> = {}): NavigationCategoryOut {
  return { id, parent_id: parent, slug: id, name: id, position: 0, product_counts: counts };
}

const NAVIGATION: NavigationOut = {
  scales: [
    { code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5, product_count: 3 },
    { code: "N", name: "N", ratio: "1:160", ratio_denominator: 160, track_gauge_mm: 9, product_count: 0 },
  ],
  categories: [category("strasse", null), category("lkw", "strasse", { H0: 3 }), category("schiene", null)],
  epochs: [],
  finishes: [],
};

describe("catalogPaths", () => {
  it("lists scales and categories with models, nothing empty", () => {
    expect(catalogPaths(NAVIGATION)).toEqual(["/katalog/h0", "/katalog/h0/strasse", "/katalog/h0/lkw"]);
  });
});

describe("sitemapEntries", () => {
  beforeEach(() => {
    fetchStoreMock.mockReset();
    vi.stubEnv("MB_PUBLIC_BASE_URL", "https://www.adp-modelle.de/");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("lists pages, catalogue and every product page by page", async () => {
    fetchStoreMock.mockImplementation((path, params) => {
      if (path === "/navigation") {
        return Promise.resolve(NAVIGATION);
      }
      return Promise.resolve(
        params?.cursor
          ? { items: [{ slug: "kipper" }], next_cursor: null }
          : { items: [{ slug: "edk-6" }], next_cursor: "seite-2" },
      );
    });
    const urls = (await sitemapEntries()).map((entry) => entry.url);
    expect(urls[0]).toBe("https://www.adp-modelle.de");
    expect(urls).toContain("https://www.adp-modelle.de/katalog/h0/lkw");
    expect(urls.slice(-2)).toEqual([
      "https://www.adp-modelle.de/produkte/edk-6",
      "https://www.adp-modelle.de/produkte/kipper",
    ]);
  });

  it("still lists the fixed pages while the API is down", async () => {
    fetchStoreMock.mockRejectedValue(ApiProblem.network(new Error("offline")));
    expect(await sitemapEntries()).toHaveLength(SITEMAP_PAGES.length);
  });
});
