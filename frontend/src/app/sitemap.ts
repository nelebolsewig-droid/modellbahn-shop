import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { sitemapEntries } from "@/lib/site/sitemap";

/** /sitemap.xml for search engines (ADR 0036), fresh on every request. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  await connection();
  return sitemapEntries();
}
