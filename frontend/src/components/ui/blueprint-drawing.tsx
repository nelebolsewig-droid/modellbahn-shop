import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Classes for the SVG parts of a drawing; strokes stay 1 px at any size (`vectorEffect`). */
export const DRAWING = {
  /** A closed outline; filled with the stage colour so the grid does not show through. */
  face: "fill-stage stroke-drawing-line",
  /** An open outline. */
  line: "fill-none stroke-drawing-line",
  /** Axes and construction lines, dashed. */
  helper: "fill-none stroke-drawing-helper [stroke-dasharray:4_3]",
  /** Dimension and extension lines. */
  dimension: "fill-none stroke-drawing-dimension",
  /** One part picked out in signal orange, e.g. the hook of a crane. */
  mark: "fill-highlight-subtle stroke-highlight-fill",
  /** Dimension figures. */
  figure: "fill-drawing-dimension font-mono text-[7px]",
} as const;

export type TitleBlockCell = { label: string; value: string };

type BlueprintDrawingProps = {
  viewBox: string;
  /** What the drawing shows, for screen readers. */
  label: string;
  /** The title block under the drawing: model, scale, view, sheet. */
  titleBlock: readonly TitleBlockCell[];
  /** Lets the drawing appear from left to right, as if a plotter drew it, once. */
  plotted?: boolean;
  className?: string;
  /** The SVG content; use the {@link DRAWING} classes and `vectorEffect="non-scaling-stroke"`. */
  children: ReactNode;
};

/**
 * A technical view of a model, drawn like an architectural plan: fine Prussian-blue
 * lines on a 16 px grid, dimension lines and a title block (docs/KONZEPT.md §11).
 */
export function BlueprintDrawing({ viewBox, label, titleBlock, plotted = false, className, children }: BlueprintDrawingProps) {
  return (
    <figure
      className={cn(
        "m-0 rounded-lg bg-stage p-6 sm:p-8",
        "bg-[image:linear-gradient(var(--drawing-grid)_1px,transparent_1px),linear-gradient(90deg,var(--drawing-grid)_1px,transparent_1px)]",
        "bg-[size:16px_16px] bg-[position:-1px_-1px]",
        className,
      )}
    >
      <svg viewBox={viewBox} role="img" aria-label={label} className={cn("block h-auto w-full overflow-visible", plotted && "animate-plot-in")}>
        {children}
      </svg>
      <figcaption
        className="mt-5 grid grid-cols-2 gap-px border border-drawing-line bg-drawing-line font-mono text-hint text-ink sm:grid-cols-[1.5fr_1fr_0.7fr_1.3fr]"
      >
        {titleBlock.map((cell) => (
          <div key={cell.label} className="bg-stage px-3 py-2">
            <span className="block text-[0.625rem] leading-[0.875rem] tracking-[0.06em] text-ink-tertiary uppercase">
              {cell.label}
            </span>
            {cell.value}
          </div>
        ))}
      </figcaption>
    </figure>
  );
}
