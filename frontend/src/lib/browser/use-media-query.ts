"use client";

import { useSyncExternalStore } from "react";

/**
 * Whether a media query matches right now, e.g. "(min-width: 80rem)". False while
 * rendering on the server and where the browser knows no media queries.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window.matchMedia !== "function") {
        return () => {};
      }
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
    () => false,
  );
}
