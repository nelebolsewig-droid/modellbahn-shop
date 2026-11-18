import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { publicBaseUrl } from "@/lib/site/sitemap";

/** /robots.txt (ADR 0036): the shop is open, the Stellwerk and personal pages are not. */
export default async function robots(): Promise<MetadataRoute.Robots> {
  await connection();
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin", "/api/", "/konto", "/kasse", "/warenkorb", "/bestellung"],
    },
    sitemap: `${publicBaseUrl()}/sitemap.xml`,
  };
}
