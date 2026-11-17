"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type RevealProps = {
  children: ReactNode;
  /** Position in a row of siblings: each one follows the one before by 90 ms. */
  index?: number;
  as?: "div" | "li" | "section";
  className?: string;
};

/**
 * Lets its content rise into place when it scrolls into view, once. What is already on
 * screen when the page opens stays as it is, and so does everything without JavaScript
 * or with reduced motion: only content still below the fold is hidden, by this effect.
 */
export function Reveal({ children, index = 0, as: Component = "div", className }: RevealProps) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    if (node.getBoundingClientRect().top < window.innerHeight * 0.92) {
      return;
    }
    node.dataset.reveal = "waiting";
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          node.dataset.reveal = "shown";
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Component
      // The three elements share what this needs; the ref's exact element type does not matter.
      ref={ref as never}
      data-reveal="shown"
      style={{ "--reveal-index": index } as CSSProperties}
      className={cn(className)}
    >
      {children}
    </Component>
  );
}
