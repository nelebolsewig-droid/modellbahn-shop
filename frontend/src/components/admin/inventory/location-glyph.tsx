import type { LocationKind } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

/** Line drawings of the five kinds of place, in the stroke of the blueprint drawings. */
const PATHS: Readonly<Record<LocationKind, string>> = {
  site: "M2.5 7.5 8 3l5.5 4.5V13h-11Z M6.5 13V9.5h3V13",
  shelf: "M3 2.5v11 M13 2.5v11 M3 5.5h10 M3 9h10 M3 12.5h10",
  compartment: "M2.5 3.5h11v9h-11Z M2.5 8h11",
  box: "M2.5 5.5h11v7h-11Z M2 3.5h12v2H2Z M6.5 8h3",
  staging: "M2 9.5h12l-1.5 3h-9Z M4.5 9.5V6h7v3.5",
};

export function LocationGlyph({ kind, className }: { kind: LocationKind; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
      strokeLinecap="round"
      className={cn("size-4 shrink-0", className)}
    >
      <path d={PATHS[kind]} />
    </svg>
  );
}
