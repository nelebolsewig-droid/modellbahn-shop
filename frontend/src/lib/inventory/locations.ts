/*
 * The store's places as a tree (backend: inventory/domain/model.py, Location.create).
 * A site is the building; directly on a site the code is the segment itself (R02),
 * further down the parent's code and the segment (R02-F04). The site's own segment
 * stays out of the codes, so the labels stay short.
 */

import type { LocationKind, LocationNodeOut } from "@/lib/api/generated/model";

import { CHILD_KINDS } from "./labels";

export const SEGMENT_PATTERN = /^[A-Z0-9]{1,8}$/;

type Parent = { kind: LocationKind; code: string } | null;

/** The code a new location below `parent` gets, as the backend will build it. */
export function childCode(parent: Parent, segment: string): string {
  const cleaned = segment.trim().toUpperCase();
  if (parent === null || parent.kind === "site") {
    return cleaned;
  }
  return `${parent.code}-${cleaned}`;
}

/** The kinds that may go below `parent` (a site at the top). */
export function childKinds(parent: Parent): readonly LocationKind[] {
  return CHILD_KINDS[parent?.kind ?? "root"];
}

/** A location and everything below it: the tree comes in path order. */
export function subtree(items: readonly LocationNodeOut[], code: string): LocationNodeOut[] {
  const start = items.findIndex((item) => item.code === code);
  if (start === -1) {
    return [];
  }
  const root = items[start] as LocationNodeOut;
  const prefix = `${root.path}.`;
  return [root, ...items.slice(start + 1).filter((item) => item.path.startsWith(prefix))];
}

/** Codes worth a label: the places goods go into, plus shelves (their front label). */
export function labelCodes(items: readonly LocationNodeOut[]): string[] {
  return items.filter((item) => item.kind !== "site").map((item) => item.code);
}
