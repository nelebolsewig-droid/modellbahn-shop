import { connection } from "next/server";

import type { StoreProductOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { SHOP_NAME } from "@/lib/config";
import { publicBaseUrl } from "@/lib/site/sitemap";
import { feedItems, feedXml, loadAvailability } from "@/lib/site/structured-data";

/** Enough for any catalogue this workshop will have; stops a runaway cursor. */
const MAX_PAGES = 50;

/**
 * /google-produkte.xml: the product feed for Google Merchant Center (ADR 0047), one row
 * per variant, fresh on every request. Merchant Center fetches it once a day.
 */
export async function GET(): Promise<Response> {
  await connection();
  const base = publicBaseUrl();
  const slugs: string[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result = await fetchStore<StoreProductPageOut>("/products", { limit: "48", sort: "name", cursor });
    if (result === null) {
      break;
    }
    slugs.push(...result.items.map((item) => item.slug));
    if (!result.next_cursor) {
      break;
    }
    cursor = result.next_cursor;
  }
  const items = [];
  for (const slug of slugs) {
    const product = await fetchStore<StoreProductOut>(`/products/${encodeURIComponent(slug)}`);
    if (product) {
      items.push(...feedItems(product, await loadAvailability(slug), base));
    }
  }
  return new Response(feedXml(items, base, SHOP_NAME, SHOP_NAME), {
    headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
