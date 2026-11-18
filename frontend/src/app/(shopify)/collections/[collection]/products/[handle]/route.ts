import { legacyRedirect, productTarget } from "@/lib/site/shopify";

/** A product opened from a collection in the former Shopify shop (ADR 0036). */
export async function GET(
  _request: Request,
  ctx: RouteContext<"/collections/[collection]/products/[handle]">,
) {
  const { handle } = await ctx.params;
  return legacyRedirect(await productTarget(handle));
}
