import { BlueprintDrawing, DRAWING } from "@/components/ui/blueprint-drawing";

const STROKE = { strokeWidth: 1, vectorEffect: "non-scaling-stroke" } as const;

/**
 * Side view of a truck crane in H0, the boom laid down for the road: the start page's
 * emblem, drawn like a construction plan. Truck cranes and lorries are the core of the
 * workshop's range; the drawing shows the kind of model, not one particular type.
 */
export function CraneTruckDrawing({ className }: { className?: string }) {
  return (
    <BlueprintDrawing
      className={className}
      viewBox="10 70 280 128"
      label="Zeichnung eines Autodrehkrans in der Seitenansicht, mit Maßlinien"
      titleBlock={[
        { label: "Zeichnung", value: "Autodrehkran" },
        { label: "Maßstab", value: "1:87 · H0" },
        { label: "Ansicht", value: "Seite" },
        { label: "Fertigung", value: "Handarbeit" },
      ]}
    >
      <g transform="translate(16 6)">
        {/* Road and the axis the superstructure turns about. */}
        <path className={DRAWING.line} d="M6 160 H238" {...STROKE} />
        <path className={DRAWING.helper} d="M178 88 V142" {...STROKE} />

        {/* Chassis, cab with wheel arch, bumper. */}
        <path className={DRAWING.face} d="M24 128 H230 V135 H24 Z" {...STROKE} />
        <path
          className={DRAWING.face}
          d="M20 128 V100 Q20 92 28 92 H58 L64 99 V128 H61 A15 15 0 0 0 31 128 Z"
          {...STROKE}
        />
        <path className={DRAWING.line} d="M25 98 H56 L60 104 V112 H25 Z" {...STROKE} />
        <path className={DRAWING.face} d="M14 122 H22 V131 H14 Z" {...STROKE} />

        {/* Outrigger box with its jack, drawn in. */}
        <path className={DRAWING.face} d="M136 135 H150 V141 H136 Z" {...STROKE} />
        <path className={DRAWING.line} d="M143 141 V149 M138 149 H148" {...STROKE} />

        {/* Superstructure: slewing ring, crane cab, machine house, counterweight. */}
        <path className={DRAWING.face} d="M118 121 H214 V128 H118 Z" {...STROKE} />
        <path className={DRAWING.face} d="M110 121 V100 H132 L137 107 V121 Z" {...STROKE} />
        <path className={DRAWING.line} d="M114 104 H130 L133 109 V114 H114 Z" {...STROKE} />
        <path className={DRAWING.face} d="M137 106 H206 V121 H137 Z" {...STROKE} />
        <path className={DRAWING.line} d="M150 110 V117 M155 110 V117 M160 110 V117 M165 110 V117" {...STROKE} />
        <path className={DRAWING.face} d="M206 99 H230 V121 H206 Z" {...STROKE} />

        {/* Luffing cylinder. */}
        <path className={DRAWING.face} d="M155 106 L150 106 L127 95 L130 92.5 Z" {...STROKE} />

        {/* Telescopic boom in three sections, laid on the rest above the cab. */}
        <path className={DRAWING.face} d="M180 96 L110 87.8 L110 95.8 L180 104 Z" {...STROKE} />
        <path className={DRAWING.face} d="M110 88.8 L50 81.7 L50 87.7 L110 94.8 Z" {...STROKE} />
        <path className={DRAWING.face} d="M50 82.7 L10 78 L10 82 L50 86.7 Z" {...STROKE} />
        <circle className={DRAWING.face} cx="178" cy="100" r="2.5" {...STROKE} />
        <circle className={DRAWING.face} cx="10" cy="80" r="3.5" {...STROKE} />
        <path className={DRAWING.line} d="M46 92 V87.5 M42 87 H52" {...STROKE} />

        {/* Hook block, hung up for the road. */}
        <path className={DRAWING.line} d="M10 83.5 V98" {...STROKE} />
        <path className={DRAWING.face} d="M6 98 H14 V106 H6 Z" {...STROKE} />
        <path className={DRAWING.line} d="M10 106 V110 A3 3 0 1 1 7 113" {...STROKE} />

        {/* Wheels: one front axle, a tandem at the back. */}
        {[46, 168, 196].map((x) => (
          <g key={x}>
            <circle className={DRAWING.face} cx={x} cy="147" r="13" {...STROKE} />
            <circle className={DRAWING.line} cx={x} cy="147" r="5" {...STROKE} />
          </g>
        ))}

        {/* Overall length below, height on the right. */}
        <path
          className={DRAWING.dimension}
          d="M14 164 V182 M230 164 V182 M14 177 H230 M10 181 L18 173 M226 181 L234 173"
          {...STROKE}
        />
        <text className={DRAWING.figure} x="122" y="174" textAnchor="middle">
          112
        </text>
        <path
          className={DRAWING.dimension}
          d="M232 96 H252 M240 160 H252 M247 96 V160 M243 100 L251 92 M243 164 L251 156"
          {...STROKE}
        />
        <text className={DRAWING.figure} transform="translate(256 128) rotate(-90)" textAnchor="middle">
          37
        </text>
      </g>
    </BlueprintDrawing>
  );
}
