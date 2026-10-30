import type { Technology } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

type PrinterGlyphProps = {
  technology: Technology;
  /** How far the plate on it has come, 0 to 1; null while nothing prints. */
  fraction: number | null;
  /** Out of service: drawn faint. */
  muted?: boolean;
  className?: string;
};

// The part grows to at most this height (viewBox units), layer by layer.
const MAX_HEIGHT = 30;
const LAYER = 2.5;

/**
 * A printer drawn like the shop's construction drawings: thin lines on the stage, the
 * part in accent blue. While a plate prints, the part grows with its progress: on
 * filament from the bed upwards under a nozzle that goes to and fro, on resin hanging
 * from the build plate, which rises out of the vat. Decorative: the card says it all in
 * words.
 */
export function PrinterGlyph({ technology, fraction, muted = false, className }: PrinterGlyphProps) {
  const printing = fraction !== null;
  const height = printing ? Math.max(LAYER, Math.min(1, fraction) * MAX_HEIGHT) : 0;
  return (
    <svg
      viewBox="0 0 120 84"
      aria-hidden="true"
      focusable="false"
      className={cn("block h-auto w-full overflow-visible", muted && "opacity-40", className)}
    >
      <g fill="none" strokeWidth={1.1} strokeLinecap="round" strokeLinejoin="round" className="stroke-drawing-line">
        {technology === "fdm" ? (
          <Filament height={height} printing={printing} />
        ) : (
          <Resin height={height} printing={printing} />
        )}
      </g>
    </svg>
  );
}

function Layers({ x, y, width, height }: { x: number; y: number; width: number; height: number }) {
  const count = Math.floor(height / LAYER);
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} className="fill-accent-subtle stroke-accent" />
      {Array.from({ length: count - 1 }, (_, index) => (
        <line
          key={index}
          x1={x + 1}
          x2={x + width - 1}
          y1={y + (index + 1) * LAYER}
          y2={y + (index + 1) * LAYER}
          className="stroke-accent"
          strokeWidth={0.4}
          opacity={0.55}
        />
      ))}
    </g>
  );
}

function Filament({ height, printing }: { height: number; printing: boolean }) {
  const bed = 64;
  // The gantry rides on top of the part, plus room for the nozzle.
  const gantry = bed - height - 10;
  return (
    <>
      {/* Frame and base */}
      <rect x={14} y={72} width={92} height={6} rx={1} className="fill-stage" />
      <line x1={22} y1={10} x2={22} y2={72} />
      <line x1={98} y1={10} x2={98} y2={72} />
      <line x1={18} y1={10} x2={102} y2={10} />
      {/* Spool on top */}
      <circle cx={60} cy={5} r={3.2} className="stroke-drawing-helper" />
      {/* Bed */}
      <rect x={30} y={bed} width={60} height={4} rx={0.6} className="fill-stage" />
      <line x1={34} y1={68} x2={34} y2={72} className="stroke-drawing-helper" />
      <line x1={86} y1={68} x2={86} y2={72} className="stroke-drawing-helper" />
      {height > 0 ? <Layers x={46} y={bed - height} width={28} height={height} /> : null}
      {/* Gantry with the print head */}
      <line x1={22} y1={gantry} x2={98} y2={gantry} />
      <g className={printing ? "animate-nozzle-sweep" : undefined}>
        <rect x={54} y={gantry - 4} width={12} height={7} rx={1} className="fill-stage" />
        <path
          d={`M57.5 ${gantry + 3} L60 ${gantry + 7} L62.5 ${gantry + 3}`}
          className={printing ? "fill-accent stroke-accent" : "fill-stage"}
        />
      </g>
    </>
  );
}

function Resin({ height, printing }: { height: number; printing: boolean }) {
  const vatFloor = 58;
  // The build plate hangs above the part that grows beneath it.
  const plate = vatFloor - 1 - height - 3;
  return (
    <>
      {/* Body with the light source */}
      <rect x={14} y={60} width={92} height={18} rx={1.5} className="fill-stage" />
      <line x1={22} y1={70} x2={60} y2={70} className="stroke-drawing-helper" />
      {/* Vat with resin */}
      <path d="M28 48 L28 58 L88 58 L88 48" className="fill-stage" />
      <line x1={30} y1={52} x2={86} y2={52} className="stroke-drawing-helper" strokeDasharray="2 2" />
      {printing ? (
        <rect
          x={44}
          y={vatFloor - 0.6}
          width={32}
          height={1.2}
          className="animate-lamp-pulse fill-accent stroke-none"
        />
      ) : null}
      {/* Z axis and arm */}
      <rect x={96} y={6} width={6} height={54} rx={1} className="fill-stage" />
      <line x1={96} y1={plate + 1.5} x2={60} y2={plate + 1.5} />
      <line x1={60} y1={plate - 6} x2={60} y2={plate} />
      {/* Build plate */}
      <rect x={42} y={plate} width={36} height={3} rx={0.6} className="fill-stage" />
      {height > 0 ? <Layers x={48} y={plate + 3} width={24} height={height} /> : null}
    </>
  );
}
