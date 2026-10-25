import Link from "next/link";

import { ScaleRule } from "@/components/ui/scale-rule";
import { SpecLine } from "@/components/ui/spec-line";
import type { NavigationScaleOut } from "@/lib/api/generated/model";
import { formatMillimetres } from "@/lib/catalog/format";
import { catalogPath, millimetresPerMetre, scaleLabel } from "@/lib/catalog/scales";

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
          {offered.map((scale) => (
            <li key={scale.code}>
              <Link
                href={catalogPath({ scale: scale.code })}
                aria-label={`${scaleLabel(scale)}, ${models(scale.product_count)}`}
                className="group flex h-full flex-col rounded-lg border border-line bg-surface p-6 transition-[border-color,box-shadow] duration-150 hover:border-ink-secondary hover:shadow-[inset_0_0_0_1px_var(--ink-secondary)]"
              >
                <span className="flex items-start justify-between gap-4">
                  <span className="text-display leading-none font-extralight tracking-[-0.03em]">{scale.name}</span>
                  <span className="mt-1 text-hint text-ink-tertiary">{models(scale.product_count)}</span>
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
                <span className="mt-4 text-small font-medium text-accent group-hover:underline group-hover:underline-offset-4">
                  Zu den Modellen in {scale.name} →
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
