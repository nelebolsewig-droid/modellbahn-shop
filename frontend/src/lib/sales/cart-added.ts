"use client";

import { useSyncExternalStore } from "react";

/*
 * "Just added to the cart": AddToCart and the phone's buy bar announce it, the panel in
 * the shop frame shows it. A tiny store instead of a context, so the panel needs no
 * provider around every page.
 */

export type CartAdded = {
  variantId: string;
  /** "IFA ADK 80 Autokran · H0 · Fertigmodell". */
  title: string;
  /** Pieces added just now. */
  quantity: number;
  /** Counts up, so adding the same thing again opens the panel again. */
  serial: number;
};

let current: CartAdded | null = null;
let serial = 0;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function announceCartAdded(added: Omit<CartAdded, "serial">): void {
  serial += 1;
  current = { ...added, serial };
  emit();
}

export function dismissCartAdded(): void {
  if (current === null) return;
  current = null;
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useCartAdded(): CartAdded | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
}
