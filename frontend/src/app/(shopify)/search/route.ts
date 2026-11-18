import type { NextRequest } from "next/server";

import { legacyRedirect, searchTarget } from "@/lib/site/shopify";

/** The search of the former Shopify shop, /search?q=… (ADR 0036). */
export function GET(request: NextRequest) {
  return legacyRedirect(searchTarget(request.nextUrl.searchParams.get("q")));
}
