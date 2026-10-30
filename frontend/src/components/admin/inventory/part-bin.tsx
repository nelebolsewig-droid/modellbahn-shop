import { cn } from "@/lib/utils";

type PartBinProps = {
  /** How full the bin is, 0 to 1 (see `binLevel`). */
  level: number;
  className?: string;
};

const COLUMNS = 6;
const ROWS = 4;

/**
 * A stacking bin as on the workshop's shelves, drawn like the construction drawings:
 * thin lines, the printed parts in accent blue, piled up to how full the box is.
 * Decorative: the numbers beside it say it in words.
 */
export function PartBin({ level, className }: PartBinProps) {
  const pieces = Math.round(Math.max(0, Math.min(1, level)) * COLUMNS * ROWS);
  return (
    <svg
      viewBox="0 0 44 34"
      aria-hidden="true"
      focusable="false"
      className={cn("block h-auto w-11 shrink-0 overflow-visible", className)}
    >
      <g fill="none" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round" className="stroke-drawing-line">
        {/* Back wall, sides and the low front with its grip. */}
        <path d="M5 4h34v26H5Z" />
        <path d="M5 16 13 12h18l8 4" />
        <path d="M17 22h10v4H17Z" opacity={0.7} />
      </g>
      <g>
        {Array.from({ length: pieces }, (_, index) => {
          const column = index % COLUMNS;
          const row = Math.floor(index / COLUMNS);
          // Stacked like loose parts: every other row shifted by half a piece.
          const x = 7 + column * 5 + (row % 2) * 2;
          const y = 26 - row * 4;
          return (
            <rect
              key={index}
              x={Math.min(x, 34)}
              y={y - 3}
              width={4}
              height={3}
              rx={0.8}
              className="fill-accent-subtle stroke-accent"
              strokeWidth={0.6}
            />
          );
        })}
      </g>
    </svg>
  );
}
