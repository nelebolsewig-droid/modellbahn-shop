/**
 * The shop's display name. The owner has not decided on one yet, so it is
 * configurable; `next build` inlines NEXT_PUBLIC_* variables into the bundle.
 */
export const SHOP_NAME = process.env.NEXT_PUBLIC_SHOP_NAME?.trim() || "Modellbahn-Shop";
