import type { Route } from "next";

import type { StoreProductOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";

import SHOPIFY_PRODUCTS from "./shopify-produkte.json";

/*
 * Addresses of the former Shopify shop on www.adp-modelle.de (ADR 0036). Search engines,
 * bookmarks and old links keep asking for them after the move; each one answers with a
 * redirect to the page that took its place instead of "Seite nicht gefunden".
 * Fixed pages (policies, cart, account) are SHOPIFY_PAGE_REDIRECTS in next.config.ts;
 * products, collections and the search need a look at the catalogue and come here,
 * through the route handlers under src/app/(shopify).
 */

/** Collections that stood for the whole range rather than one category. */
const WHOLE_RANGE = new Set(["all", "frontpage", "alle", "alle-produkte", "startseite"]);

/** A handle as Shopify writes it: lower-case letters, digits, hyphens. */
const HANDLE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export type LegacyTarget = Readonly<{
  path: Route;
  /** 301 when the page is certainly the right one, 302 for a best guess. */
  permanent: boolean;
}>;

/**
 * Handles whose product got another address here, from the Shopify export
 * (scripts/shopify_weiterleitungen.py writes shopify-produkte.json). Products whose
 * address stayed the same need no entry.
 */
const RENAMED: Readonly<Record<string, string>> = SHOPIFY_PRODUCTS;

/** Next.js hands route parameters over decoded already. */
function normalise(handle: string): string {
  return handle.trim().toLowerCase();
}

/** "kran-edk-6-h0" → "kran edk 6 h0": the words of a handle, for the catalogue search. */
export function searchWords(handle: string): string {
  return normalise(handle).replace(/[^a-z0-9äöüß]+/g, " ").trim().slice(0, 200);
}

function catalogueSearch(words: string): LegacyTarget {
  const query = words ? `?${new URLSearchParams({ suche: words }).toString()}` : "";
  return { path: `/katalog${query}` as Route, permanent: false };
}

/**
 * Where /products/<handle> lives now: the renamed product, the product with the same
 * address, or else (a product that is gone, or the API is down) the catalogue search
 * for its words, as a temporary redirect, so that a later entry can still take over.
 */
export async function productTarget(rawHandle: string): Promise<LegacyTarget> {
  const handle = normalise(rawHandle);
  if (!HANDLE.test(handle)) {
    return catalogueSearch(searchWords(handle));
  }
  const renamed = RENAMED[handle];
  if (renamed) {
    return { path: `/produkte/${encodeURIComponent(renamed)}` as Route, permanent: true };
  }
  try {
    const product = await fetchStore<StoreProductOut>(`/products/${encodeURIComponent(handle)}`);
    if (product !== null) {
      return { path: `/produkte/${encodeURIComponent(product.slug)}` as Route, permanent: true };
    }
  } catch {
    // The API is unreachable: the search page shows its own error, nothing is cached.
  }
  return catalogueSearch(searchWords(handle));
}

/**
 * Where /collections/<handle> lives now. The catalogue page itself redirects
 * ?kategorie=<slug> to the scale with most models of that category (see katalog/page.tsx)
 * and shows the whole range for a category it does not know.
 */
export function collectionTarget(rawHandle: string): LegacyTarget {
  const handle = normalise(rawHandle);
  if (WHOLE_RANGE.has(handle) || !HANDLE.test(handle)) {
    return { path: "/katalog", permanent: true };
  }
  return { path: `/katalog?kategorie=${encodeURIComponent(handle)}` as Route, permanent: true };
}

/** Where Shopify's /search?q=… lives now. */
export function searchTarget(query: string | null): LegacyTarget {
  const words = (query ?? "").trim().slice(0, 200);
  return { ...catalogueSearch(words), permanent: true };
}

/**
 * The redirect itself. The Location is relative: behind Caddy, Next.js does not know
 * the public scheme, and an absolute http:// address would cost another hop.
 */
export function legacyRedirect(target: LegacyTarget): Response {
  return new Response(null, {
    status: target.permanent ? 301 : 302,
    headers: {
      Location: target.path,
      // A guess may become a certain answer once shopify-produkte.json has its entry.
      "Cache-Control": target.permanent ? "public, max-age=86400" : "no-store",
    },
  });
}
