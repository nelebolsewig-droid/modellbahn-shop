import { Fragment } from "react";

import { cn } from "@/lib/utils";

type SpecLineProps = {
  /** In this order: gauge, scale, technique, optionally the finish ("H0", "1:87", "Resin"). */
  values: readonly string[];
  size?: "large" | "small";
  className?: string;
};

/** The technical line of a model, large and thin: „H0 · 1:87 · Resin“. */
export function SpecLine({ values, size = "large", className }: SpecLineProps) {
  return (
    <p
      className={cn(
        "flex flex-wrap items-baseline gap-x-[0.45em] tabular-nums",
        size === "large" ? "text-spec text-ink" : "text-[0.9375rem] leading-[1.375rem] text-ink-secondary",
        className,
      )}
    >
      {values.map((value, index) => (
        <Fragment key={value}>
          {index > 0 ? (
            <span aria-hidden="true" className="text-ink-tertiary">
              ·
            </span>
          ) : null}
          <span>{value}</span>
        </Fragment>
      ))}
    </p>
  );
}
