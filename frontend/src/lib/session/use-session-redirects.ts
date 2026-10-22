"use client";

import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { loginPath, type Area } from "@/lib/navigation";

import type { Session, SessionCache } from "./session";

/** Sends a visitor who is (or just became) logged in on to `target`. */
export function useRedirectWhenAuthenticated(session: Session<unknown>, target: Route): void {
  const router = useRouter();
  const authenticated = session.status === "authenticated";

  useEffect(() => {
    if (authenticated) {
      router.replace(target);
    }
  }, [authenticated, target, router]);
}

/**
 * For pages that need a login. The proxy only checks that a cookie exists; this
 * hook reacts to what the API says: a visitor without a valid session (never had
 * one, expired, revoked elsewhere) goes to the login page and comes back afterwards.
 *
 * `leave` is for the page's own logout and account deletion: it forgets the session
 * and navigates away without the detour over the login page.
 */
export function useProtectedArea<TAccount>(
  session: Session<TAccount>,
  cache: SessionCache<TAccount>,
  area: Area,
): { leave: (target: Route) => void } {
  const router = useRouter();
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);
  const anonymous = session.status === "anonymous";

  useEffect(() => {
    if (anonymous && !leaving) {
      router.replace(loginPath(area, pathname));
    }
  }, [anonymous, leaving, router, area, pathname]);

  const leave = useCallback(
    (target: Route) => {
      setLeaving(true);
      cache.clear();
      router.replace(target);
    },
    [cache, router],
  );

  return { leave };
}
