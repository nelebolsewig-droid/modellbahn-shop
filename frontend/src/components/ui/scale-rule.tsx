import { millimetresPerMetre } from "@/lib/catalog/scales";

const millimetres = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });

type ScaleRuleProps = {
  /** 87 for 1:87. */
  ratioDenominator: number;
  /** The longest rule in the same row, so that all of them share one millimetre. */
  longestMillimetres: number;
  className?: string;
};

/**
 * A measuring tape: how long one metre of the original is in this scale, drawn in true
 * proportion to the other scales of the row: 1:220 a stub, 1:22,5 four times H0.
 * Millimetre ticks, longer every five and ten; the length is also written out.
 */
export function ScaleRule({ ratioDenominator, longestMillimetres, className }: ScaleRuleProps) {
  const length = millimetresPerMetre(ratioDenominator);
  const ticks = Array.from({ length: Math.floor(length) + 1 }, (_, mm) => mm);
  return (
    // The tape spans the full width in every tile, so equal widths mean equal millimetres.
    <div className={className}>
      <svg
        aria-hidden="true"
        viewBox={`0 0 ${longestMillimetres} 7`}
        preserveAspectRatio="none"
        className="block h-3.5 w-full text-ink"
      >
        <rect x="0" y="0" width={length} height="7" className="fill-stage" />
        <line x1="0" y1="0.5" x2={length} y2="0.5" stroke="currentColor" vectorEffect="non-scaling-stroke" />
        {ticks.map((mm) => (
          <line
            key={mm}
            x1={mm}
            x2={mm}
            y1="0.5"
            y2={mm % 10 === 0 ? 7 : mm % 5 === 0 ? 5 : 3}
            stroke="currentColor"
            strokeOpacity={mm % 5 === 0 ? 1 : 0.55}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <line x1={length} x2={length} y1="0" y2="7" className="stroke-accent" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="mt-1.5 font-mono text-hint text-ink-tertiary tabular-nums">
        1 m ≙ {millimetres.format(length)} mm
      </p>
    </div>
  );
}
