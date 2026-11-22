"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { recordVisit } from "@/lib/api/generated/store-site/store-site";

/**
 * Counts each page of the shop once (ADR 0043): no cookie, no storage, nothing about the
 * visitor leaves the server. A failed count is no reason to bother anyone.
 */
export function VisitBeacon() {
  const pathname = usePathname();
  useEffect(() => {
    recordVisit().catch(() => undefined);
  }, [pathname]);
  return null;
}
