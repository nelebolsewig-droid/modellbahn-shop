import type { Route } from "next";

import type { NavigationCategoryOut } from "@/lib/api/generated/model";

/*
 * Scales (Maßstäbe) as the shop shows them: H0 · 1:87, 1:24. The shop is sorted by
 * scale first, then by category; every list has its own address below /katalog.
 */

type NamedScale = { code: string; name: string; ratio: string };

/** "H0 · 1:87"; a scale named after its ratio ("1:24") is not written twice. */
export function scaleLabel(scale: NamedScale): string {
  return scale.name === scale.ratio ? scale.ratio : `${scale.name} · ${scale.ratio}`;
}

/** The scale's part of an address: H0 → "h0", 124 → "124". */
export function scaleSlug(code: string): string {
  return code.toLowerCase();
}

/** The scale an address names, ignoring letter case. */
export function findScale<T extends { code: string }>(scales: readonly T[], slug: string): T | undefined {
  const wanted = slug.toLowerCase();
  return scales.find((scale) => scaleSlug(scale.code) === wanted);
}

/** How long one metre of the original is in the model: 1:87 → 11.49 mm. */
export function millimetresPerMetre(ratioDenominator: number): number {
  return 1000 / ratioDenominator;
}

export type CatalogLocation = {
  /** The scale's code, e.g. "H0". */
  scale: string;
  /** A category's slug; its subcategories are included. */
  category?: string;
  epoche?: string;
  suche?: string;
  sortierung?: string;
  /** Cursor of the next page. */
  weiter?: string;
};

const QUERY_ORDER = ["epoche", "suche", "sortierung", "weiter"] as const;

/** The address of a list: /katalog/h0/lkw?epoche=III. Empty filters are left out. */
export function catalogPath(location: CatalogLocation): Route {
  const path = [`/katalog/${encodeURIComponent(scaleSlug(location.scale))}`];
  if (location.category) {
    path.push(encodeURIComponent(location.category));
  }
  const params = new URLSearchParams();
  // A fixed order: the same list always has the same address.
  for (const name of QUERY_ORDER) {
    const value = location[name];
    if (value) {
      params.set(name, value);
    }
  }
  const query = params.toString();
  return `${path.join("/")}${query ? `?${query}` : ""}` as Route;
}

/** Products in the shop in this category and all below it, in one scale. */
export function branchCount(
  categories: readonly NavigationCategoryOut[],
  categoryId: string,
  scaleCode: string,
): number {
  const children = new Map<string | null, NavigationCategoryOut[]>();
  for (const category of categories) {
    children.set(category.parent_id, [...(children.get(category.parent_id) ?? []), category]);
  }
  let total = 0;
  const seen = new Set<string>();
  const stack = [categoryId];
  while (stack.length > 0) {
    const id = stack.pop() as string;
    if (seen.has(id)) {
      continue; // A cycle would be a bug in the data; it must not hang the page.
    }
    seen.add(id);
    total += categories.find((category) => category.id === id)?.product_counts[scaleCode] ?? 0;
    stack.push(...(children.get(id) ?? []).map((child) => child.id));
  }
  return total;
}

/** The scale with the most products in this branch, e.g. for an address without a scale. */
export function busiestScale<T extends { code: string }>(
  scales: readonly T[],
  categories: readonly NavigationCategoryOut[],
  categoryId: string,
): T | undefined {
  let best: { scale: T; count: number } | undefined;
  for (const scale of scales) {
    const count = branchCount(categories, categoryId, scale.code);
    if (count > 0 && (best === undefined || count > best.count)) {
      best = { scale, count };
    }
  }
  return best?.scale;
}
