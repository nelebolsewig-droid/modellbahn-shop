import { CUSTOMER_AREA, STAFF_AREA, type Area } from "./navigation";

/** Session cookies set by the API (HttpOnly; only their presence is visible here). */
export const CUSTOMER_COOKIE = "mb_session";
export const STAFF_COOKIE = "mb_admin";

/** Pages under /konto that work without being logged in. */
const PUBLIC_CUSTOMER_PAGES: ReadonlySet<string> = new Set([
  "/konto/anmelden",
  "/konto/registrieren",
  "/konto/bestaetigen",
  "/konto/bestaetigung-erneut",
  "/konto/passwort-vergessen",
  "/konto/passwort-zuruecksetzen",
]);

const PUBLIC_STAFF_PAGES: ReadonlySet<string> = new Set(["/admin/anmelden"]);

export type Protection = { cookie: string; area: Area };

const isWithin = (pathname: string, root: string): boolean =>
  pathname === root || pathname.startsWith(`${root}/`);

/**
 * Which session a page needs, or null for public pages. New pages below /konto and
 * /admin are protected unless they are listed as public above.
 */
export function protectionFor(pathname: string): Protection | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (isWithin(path, CUSTOMER_AREA.home) && !PUBLIC_CUSTOMER_PAGES.has(path)) {
    return { cookie: CUSTOMER_COOKIE, area: CUSTOMER_AREA };
  }
  if (isWithin(path, STAFF_AREA.home) && !PUBLIC_STAFF_PAGES.has(path)) {
    return { cookie: STAFF_COOKIE, area: STAFF_AREA };
  }
  return null;
}
