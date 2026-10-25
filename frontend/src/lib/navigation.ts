import type { Route } from "next";

/** Query parameter that carries the page to return to after logging in. */
export const RETURN_TO_PARAM = "weiter";

export type Area = {
  /** Where to go after login when no (valid) return path is given. */
  home: Route;
  login: Route;
  /** Pages outside the area that a login may return to (the checkout). */
  returnTo?: readonly string[];
};

export const CUSTOMER_AREA = {
  home: "/konto",
  login: "/konto/anmelden",
  returnTo: ["/kasse"],
} as const satisfies Area;
export const STAFF_AREA = { home: "/admin", login: "/admin/anmelden" } as const satisfies Area;

const PLACEHOLDER_ORIGIN = "http://placeholder.invalid";

/**
 * The return path from a login link, if it is safe to follow: a path inside the
 * same area of this site (or one of its ``returnTo`` pages). Anything else (other hosts, protocol-relative URLs,
 * backslash tricks, the login page itself) falls back to the area's home page.
 */
export function safeReturnPath(value: string | null | undefined, area: Area): Route {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return area.home;
  }
  let url: URL;
  try {
    url = new URL(value, PLACEHOLDER_ORIGIN);
  } catch {
    return area.home;
  }
  const inArea =
    url.pathname === area.home ||
    url.pathname.startsWith(`${area.home}/`) ||
    (area.returnTo?.includes(url.pathname) ?? false);
  if (url.origin !== PLACEHOLDER_ORIGIN || !inArea || url.pathname === area.login) {
    return area.home;
  }
  return `${url.pathname}${url.search}` as Route;
}

/** The login page of an area, remembering where the visitor wanted to go. */
export function loginPath(area: Area, returnTo: string): Route {
  const query = new URLSearchParams({ [RETURN_TO_PARAM]: returnTo });
  return `${area.login}?${query.toString()}` as Route;
}
