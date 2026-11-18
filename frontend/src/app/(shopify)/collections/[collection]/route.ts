import { collectionTarget, legacyRedirect } from "@/lib/site/shopify";

/** A collection of the former Shopify shop (ADR 0036). */
export async function GET(_request: Request, ctx: RouteContext<"/collections/[collection]">) {
  const { collection } = await ctx.params;
  return legacyRedirect(collectionTarget(collection));
}
