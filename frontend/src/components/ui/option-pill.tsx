"use client";

import { Indicator, Item, Root } from "@radix-ui/react-radio-group";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

type OptionGroupProps = Omit<ComponentProps<typeof Root>, "orientation"> & {
  /** Visible caption above the pills; also the group's accessible name. */
  label: string;
  /** Shown next to the caption, e.g. the chosen value ("Bemalt"). */
  aside?: ReactNode;
};

/**
 * One choice out of a few: gauge, finish, technique. A radio group (Radix): arrow keys
 * move between the options, Tab leaves the group.
 */
export function OptionGroup({ label, aside, className, children, ...props }: OptionGroupProps) {
  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-4">
        <p className="label-caps text-ink-tertiary" aria-hidden="true">
          {label}
        </p>
        {aside ? <p className="text-hint text-ink-tertiary">{aside}</p> : null}
      </div>
      <Root aria-label={label} orientation="horizontal" className="mt-3 flex flex-wrap gap-2" {...props}>
        {children}
      </Root>
    </div>
  );
}

type OptionPillProps = ComponentProps<typeof Item> & {
  /** "selected" is matte black, "accent" Prussian blue (for a second, quieter group). */
  tone?: "selected" | "accent";
  /** Offered, but not available right now: dashed outline, still selectable. */
  unavailable?: boolean;
};

/** A pill with a hairline outline; the chosen one is filled. */
export function OptionPill({
  tone = "selected",
  unavailable = false,
  className,
  children,
  ...props
}: OptionPillProps) {
  return (
    <Item
      className={cn(
        "inline-flex h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-full border px-5",
        "text-[0.9375rem] font-medium transition-[background-color,border-color,color] duration-150",
        "border-line-strong bg-surface text-ink hover:border-ink",
        "disabled:cursor-not-allowed disabled:text-ink-disabled disabled:hover:border-line-strong",
        unavailable && "border-dashed text-ink-tertiary",
        tone === "selected"
          ? "data-[state=checked]:border-selected data-[state=checked]:bg-selected data-[state=checked]:text-on-selected"
          : "data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-on-accent",
        "werkstatt:h-9 werkstatt:px-4 werkstatt:text-sm",
        className,
      )}
      {...props}
    >
      {children}
      {/* Radix needs the indicator for its state; the pill's colours carry it visually. */}
      <Indicator className="sr-only" />
    </Item>
  );
}
