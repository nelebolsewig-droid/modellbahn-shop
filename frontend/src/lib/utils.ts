import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * The type scale of globals.css (`--text-hint`, `--text-heading` …). tailwind-merge only
 * knows Tailwind's own sizes and would take `text-hint` for a colour, so `text-hint
 * text-success` lost its size.
 */
export const FONT_SIZES = ["display-xl", "display", "title", "heading", "spec", "body-lg", "body", "small", "hint", "label"];

const twMerge = extendTailwindMerge({
  extend: { theme: { text: FONT_SIZES } },
});

/** Joins class names; later Tailwind utilities override conflicting earlier ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
