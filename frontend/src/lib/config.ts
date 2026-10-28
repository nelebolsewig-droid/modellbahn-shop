/**
 * The shop's display name ("adp-Modelle" in .env.example). Configurable, so a test or demo
 * stack can carry its own; `next build` inlines NEXT_PUBLIC_* variables into the bundle.
 */
export const SHOP_NAME = process.env.NEXT_PUBLIC_SHOP_NAME?.trim() || "Modellbahn-Shop";
