import { BlueprintDrawing, DRAWING } from "@/components/ui/blueprint-drawing";

const STROKE = { strokeWidth: 1, vectorEffect: "non-scaling-stroke" } as const;

/**
 * South elevation of the signal box "Stellwerk Altenau" in H0: the shop's emblem on
 * the start page, drawn like a construction plan that is still in progress.
 */
export function SignalBoxDrawing({ className }: { className?: string }) {
  return (
    <BlueprintDrawing
      className={className}
      viewBox="0 0 300 214"
      label="Zeichnung des Stellwerks Altenau in der Ansicht von Süden, mit Maßlinien"
      titleBlock={[
        { label: "Zeichnung", value: "Stellwerk Altenau" },
        { label: "Maßstab", value: "1:87 · H0" },
        { label: "Ansicht", value: "Süd" },
        { label: "Stand", value: "in Konstruktion" },
      ]}
    >
      <g transform="translate(30 12)">
        <path className={DRAWING.helper} d="M120 14 V172" {...STROKE} />
        <path className={DRAWING.line} d="M24 160 H216" {...STROKE} />
        <path className={DRAWING.face} d="M70 160 V100 H62 V62 H178 V100 H170 V160 Z" {...STROKE} />
        <path className={DRAWING.face} d="M54 62 L120 26 L186 62 Z" {...STROKE} />
        <path
          className={DRAWING.line}
          d="M72 70 h20 v22 h-20 Z M98 70 h20 v22 h-20 Z M124 70 h20 v22 h-20 Z M150 70 h20 v22 h-20 Z M110 160 V128 H130 V160 Z M80 116 h16 v20 h-16 Z M144 116 h16 v20 h-16 Z"
          {...STROKE}
        />
        <path className={DRAWING.dimension} d="M62 164 V184 M178 164 V184 M62 179 H178 M58 183 L66 175 M174 183 L182 175" {...STROKE} />
        <text className={DRAWING.figure} x="120" y="175" textAnchor="middle">
          116
        </text>
        <path className={DRAWING.dimension} d="M124 26 H204 M182 160 H204 M199 26 V160 M195 30 L203 22 M195 164 L203 156" {...STROKE} />
        <text className={DRAWING.figure} transform="translate(208 93) rotate(-90)" textAnchor="middle">
          134
        </text>
        <path className={DRAWING.dimension} d="M40 70 H60 M40 92 H60 M45 70 V92 M41 74 L49 66 M41 96 L49 88" {...STROKE} />
        <text className={DRAWING.figure} transform="translate(39 81) rotate(-90)" textAnchor="middle">
          22
        </text>
      </g>
    </BlueprintDrawing>
  );
}
