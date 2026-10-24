"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Callout, type Tone } from "@/components/ui/alert";

type ResultPanelProps = {
  tone: Tone;
  title: string;
  children?: ReactNode;
};

/**
 * Replaces a form once it has done its job ("Check your inbox", "Password changed").
 * Focus moves to the panel, so keyboard and screen-reader users land on the result
 * instead of on a button that no longer exists.
 */
export function ResultPanel({ tone, title, children }: ResultPanelProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div
      ref={ref}
      tabIndex={-1}
      role={tone === "danger" ? "alert" : "status"}
      className="rounded-sm outline-offset-4"
    >
      <Callout tone={tone} title={title}>
        {children}
      </Callout>
    </div>
  );
}
