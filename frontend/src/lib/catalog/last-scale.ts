"use client";

import type { Route } from "next";
import { useEffect, useSyncExternalStore } from "react";

import { catalogPath } from "@/lib/catalog/scales";

/*
 * The scale a visitor last browsed, kept in this browser only (localStorage, no cookie,
 * nothing sent anywhere). The catalogue link in the header then leads straight to the
 * models in that scale; the scale tiles stay one click away.
 */

const KEY = "adp.massstab";

export type LastScale = { code: string; name: string };

const listeners = new Set<() => void>();
let cached: { raw: string | null; value: LastScale | null } = {
  raw: null,
  value: null,
};

function read(): LastScale | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (raw !== cached.raw) {
    let value: LastScale | null = null;
    try {
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (
        parsed !== null &&
        typeof parsed === "object" &&
        typeof (parsed as LastScale).code === "string" &&
        typeof (parsed as LastScale).name === "string"
      ) {
        value = {
          code: (parsed as LastScale).code,
          name: (parsed as LastScale).name,
        };
      }
    } catch {
      value = null;
    }
    cached = { raw, value };
  }
  return cached.value;
}

export function rememberScale(scale: LastScale): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ code: scale.code, name: scale.name }));
  } catch {
    return;
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** The remembered scale; null on the server and before anything was browsed. */
export function useLastScale(): LastScale | null {
  return useSyncExternalStore(subscribe, read, () => null);
}

/** Where "Katalog" leads: the remembered scale, or the choice of scales. */
export function useCatalogHref(): Route {
  const last = useLastScale();
  return last ? catalogPath({ scale: last.code }) : "/katalog";
}

/** Rendered by a scale's catalogue page: remembers it for the next visit. */
export function RememberScale({ code, name }: LastScale) {
  useEffect(() => rememberScale({ code, name }), [code, name]);
  return null;
}
