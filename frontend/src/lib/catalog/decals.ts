/*
 * Decals stand beside the models: the category branch "decals" (Migration 0037) is
 * created like any other in the Stellwerk, but the shop shows it under its own heading
 * and leaves it out of "Modelle".
 */

import type { Route } from "next";

import { catalogPath } from "@/lib/catalog/scales";

export const DECALS_SLUG = "decals";

type Node = { id: string; parent_id: string | null; slug: string };

/** The slug of the top-level category a category belongs to. */
function rootSlug<T extends Node>(byId: Map<string, T>, category: T): string {
  let current = category;
  const seen = new Set<string>();
  while (current.parent_id !== null && !seen.has(current.id)) {
    seen.add(current.id);
    const parent = byId.get(current.parent_id);
    if (parent === undefined) break;
    current = parent;
  }
  return current.slug;
}

/** The categories of one side of the shop: the decals or everything else (the models). */
export function categoriesOf<T extends Node>(categories: readonly T[], decals: boolean): T[] {
  const byId = new Map(categories.map((category) => [category.id, category]));
  return categories.filter((category) => (rootSlug(byId, category) === DECALS_SLUG) === decals);
}

/** Where "Decals" leads: the decals in the scale browsed last, or the overview. */
export function decalsPath(scale: string | undefined): Route {
  return scale ? catalogPath({ scale, category: DECALS_SLUG }) : "/decals";
}
