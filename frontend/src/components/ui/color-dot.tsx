import { colorSwatch } from "@/lib/catalog/colors";
import { cn } from "@/lib/utils";

type ColorDotProps = {
  /** The colour as the workshop names it: "Gelb", "Hellblau", "Rot-Weiß". */
  color: string;
  size?: "sm" | "md";
  className?: string;
};

/**
 * A round paint swatch, decorative: the colour's name always stands next to it. A hairline
 * inside keeps white and ivory visible on white; a name without a known paint gets a
 * hatched dot instead of a guess.
 */
export function ColorDot({ color, size = "md", className }: ColorDotProps) {
  const swatch = colorSwatch(color);
  return (
    <span
      aria-hidden="true"
      data-swatch={swatch === null ? "unknown" : "paint"}
      className={cn(
        "inline-block shrink-0 rounded-full shadow-[inset_0_0_0_1px_rgb(0_0_0/0.18)]",
        size === "md" ? "size-5" : "size-3.5",
        swatch === null &&
          "bg-surface bg-[image:repeating-linear-gradient(135deg,var(--line-strong)_0_1.5px,transparent_1.5px_4px)]",
        className,
      )}
      style={swatch === null ? undefined : { background: swatch }}
    />
  );
}
