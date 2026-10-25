"use client";

import { Item } from "@radix-ui/react-radio-group";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

import { SpecLine } from "./spec-line";

type ScaleTileProps = ComponentProps<typeof Item> & {
  /** The scale's name in large thin type, e.g. "H0" or "1:24". */
  name: string;
  /** Ratio and track, e.g. ["1:87", "Gleis 16,5 mm"]. */
  spec: readonly string[];
  /** A note below, e.g. the lowest price in this scale. */
  note?: string;
};

/**
 * The large choice of a scale: „H0 · 1:87 · Gleis 16,5 mm“. Belongs in an OptionGroup;
 * the chosen tile gets a matte black outline.
 */
export function ScaleTile({ name, spec, note, className, ...props }: ScaleTileProps) {
  return (
    <Item
      className={cn(
        "group flex min-w-40 flex-1 basis-40 cursor-pointer flex-col items-start rounded-md border bg-surface px-5 py-4 text-left sm:flex-none",
        "border-line-strong transition-[border-color,box-shadow] duration-150 hover:border-ink-secondary",
        "data-[state=checked]:border-selected data-[state=checked]:shadow-[inset_0_0_0_1px_var(--selected)]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    >
      <span className="text-title leading-none font-extralight">{name}</span>
      <SpecLine values={spec} size="small" className="mt-2 flex-nowrap whitespace-nowrap" />
      {note ? <span className="mt-2 text-hint text-ink-tertiary">{note}</span> : null}
    </Item>
  );
}
