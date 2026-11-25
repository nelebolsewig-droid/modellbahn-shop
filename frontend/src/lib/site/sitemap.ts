import type { MetadataRoute } from "next";

import type { NavigationOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { branchCount, catalogPath } from "@/lib/catalog/scales";

/** Pages of the shop that stand on their own; checkout, cart and account stay out. */
export const SITEMAP_PAGES = [
  "/",
  "/katalog",
  "/so-entsteht-ein-modell",
  "/der-weg-zum-perfekten-modell",
  "/in-planung",
  "/sonderanfertigung",
  "/termine",
  "/ueber-uns",
  "/versand",
  "/impressum",
  "/agb",
  "/datenschutz",
  "/widerruf",
] as const;

/** Enough for any catalogue this workshop will have; stops a runaway cursor. */
const MAX_PRODUCT_PAGES = 100;

/**
 * The shop's public address (MB_PUBLIC_BASE_URL, the same as for links in e-mails),
 * without a trailing slash. Read per request: the image is built once for every host.
 */
export function publicBaseUrl(): string {
  return (process.env.MB_PUBLIC_BASE_URL || "https://localhost").replace(/\/+$/, "");
}

/** Every scale, and every category within a scale, that has something to show. */
export function catalogPaths(navigation: NavigationOut): string[] {
  const paths: string[] = [];
  for (const scale of navigation.scales) {
    if (scale.product_count === 0) {
      continue;
    }
    paths.push(catalogPath({ scale: scale.code }));
    for (const category of navigation.categories) {
      if (branchCount(navigation.categories, category.id, scale.code) > 0) {
        paths.push(catalogPath({ scale: scale.code, category: category.slug }));
      }
    }
  }
  return paths;
}

async function productPaths(): Promise<string[]> {
  const paths: string[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_PRODUCT_PAGES; page += 1) {
    const result = await fetchStore<StoreProductPageOut>("/products", {
      limit: "48",
      sort: "name",
      cursor,
    });
    if (result === null) {
      break;
    }
    paths.push(...result.items.map((item) => `/produkte/${encodeURIComponent(item.slug)}`));
    if (!result.next_cursor) {
      break;
    }
    cursor = result.next_cursor;
  }
  return paths;
}

/**
 * The entries of /sitemap.xml. While the API is unreachable it lists the fixed pages
 * only, instead of answering 500 to a search engine.
 */
export async function sitemapEntries(): Promise<MetadataRoute.Sitemap> {
  const base = publicBaseUrl();
  let dynamic: string[] = [];
  try {
    const navigation = await fetchStore<NavigationOut>("/navigation");
    dynamic = [...(navigation ? catalogPaths(navigation) : []), ...(await productPaths())];
  } catch {
    dynamic = [];
  }
  return [...SITEMAP_PAGES, ...dynamic].map((path) => ({
    url: `${base}${path === "/" ? "" : path}`,
  }));
}
