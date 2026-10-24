"use client";

import { createContext, use, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** "werkstatt": the admin area's controls, one step more compact (the `werkstatt:` variant). */
export type Density = "werkstatt";

const DensityContext = createContext<Density | undefined>(undefined);

type DensityScopeProps = {
  density: Density;
  className?: string;
  children: ReactNode;
};

/**
 * Sets the density for everything inside. Content rendered into a portal (dialogs)
 * leaves this element in the DOM, so it reads the density from the context via
 * {@link useDensity} and sets it again.
 */
export function DensityScope({ density, className, children }: DensityScopeProps) {
  return (
    <DensityContext value={density}>
      <div data-density={density} className={cn("bg-canvas text-ink", className)}>
        {children}
      </div>
    </DensityContext>
  );
}

export function useDensity(): Density | undefined {
  return use(DensityContext);
}
