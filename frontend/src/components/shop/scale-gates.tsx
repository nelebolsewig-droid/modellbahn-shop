import Link from "next/link";

import { ScaleRule } from "@/components/ui/scale-rule";
import { SpecLine } from "@/components/ui/spec-line";
import type { NavigationScaleOut } from "@/lib/api/generated/model";
import { formatMillimetres } from "@/lib/catalog/format";
import { catalogPath, millimetresPerMetre, scaleLabel } from "@/lib/catalog/scales";

const TILE_TONES = [
  { rule: "bg-highlight-fill", ink: "text-highlight-ink", chip: "bg-highlight-subtle text-highlight-ink" },
  { rule: "bg-plum", ink: "text-plum", chip: "bg-plum-subtle text-plum" },
  { rule: "bg-sea", ink: "text-sea", chip: "bg-sea-subtle text-sea" },
  { rule: "bg-rose", ink: "text-rose", chip: "bg-rose-subtle text-rose" },
  { rule: "bg-sky", ink: "text-sky", chip: "bg-sky-subtle text-sky" },
] as const;

function models(count: number): string {
  return count === 1 ? "1 Modell" : `${count} Modelle`;
}

/**
 * The way into the catalogue: one tile per scale with models, the smallest first. A
 * measuring tape on each tile shows one metre of the original in that scale, all
 * tapes in the same millimetres. Scales without models yet are named below.
 */
export function ScaleGates({ scales }: { scales: readonly NavigationScaleOut[] }) {
  const offered = scales.filter((scale) => scale.product_count > 0);
  const waiting = scales.filter((scale) => scale.product_count === 0);
  const longest = Math.max(...offered.map((scale) => millimetresPerMetre(scale.ratio_denominator)));

  return (
    <div>
      {offered.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {offered.map((scale, index) => (
            <li key={scale.code}>
              <Link
                href={catalogPath({ scale: scale.code })}
                aria-label={`${scaleLabel(scale)}, ${models(scale.product_count)}`}
                className="group relative flex h-full flex-col overflow-hidden rounded-lg border border-line bg-surface p-6 transition-[border-color,box-shadow,transform] duration-300 ease-settle hover:-translate-y-1 hover:border-transparent hover:shadow-lift"
              >
                {/* Each scale's tile wears one colour of the palette along its top edge. */}
                <span aria-hidden="true" className={`absolute inset-x-0 top-0 h-1.5 ${TILE_TONES[index % TILE_TONES.length]?.rule}`} />
                <span className="flex items-start justify-between gap-4">
                  <span className={`text-display leading-none font-semibold tracking-[-0.04em] ${TILE_TONES[index % TILE_TONES.length]?.ink}`}>
                    {scale.name}
                  </span>
                  <span className={`mt-1 rounded-full px-2.5 py-0.5 text-hint font-medium ${TILE_TONES[index % TILE_TONES.length]?.chip}`}>
                    {models(scale.product_count)}
                  </span>
                </span>
                <SpecLine
                  values={[
                    ...(scale.name === scale.ratio ? [] : [scale.ratio]),
                    scale.track_gauge_mm === null ? "ohne Gleis" : `Gleis ${formatMillimetres(scale.track_gauge_mm)}`,
                  ]}
                  size="small"
                  className="mt-4"
                />
                <ScaleRule ratioDenominator={scale.ratio_denominator} longestMillimetres={longest} className="mt-auto pt-8" />
                <span className="mt-4 text-small font-medium text-accent transition-colors group-hover:text-highlight-ink">
                  Zu den Modellen in {scale.name}{" "}
                  <span aria-hidden="true" className="inline-block transition-transform duration-300 ease-settle group-hover:translate-x-1">
                    →
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-lg bg-stage px-8 py-16 text-center text-ink-secondary">
          Die ersten Modelle werden gerade fotografiert.
        </p>
      )}
      {waiting.length > 0 ? (
        <p className="mt-8 text-small text-ink-tertiary">
          Noch ohne Modelle: {waiting.map((scale) => scaleLabel(scale)).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
