import { cn } from "@/lib/utils";

const TRACK = "fill-none stroke-ink";
const LABEL = "fill-ink-muted font-mono";

/**
 * Track plan of a small station, drawn like a signal-box diagram. Purely decorative
 * (aria-hidden); the dashed amber track is the part "under construction".
 */
export function TrackPlan({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 520 340"
      aria-hidden="true"
      className={cn("h-auto w-full", className)}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="1" y="1" width="518" height="338" rx="6" className="fill-surface-raised stroke-line-strong" strokeWidth="1.5" />
      <text x="24" y="34" fontSize="12" letterSpacing="1.4" className={LABEL}>
        GLEISPLAN · BF ALTENAU
      </text>
      <text x="496" y="34" fontSize="12" letterSpacing="1.4" textAnchor="end" className={LABEL}>
        H0 · 1:87
      </text>
      <line x1="0" y1="50" x2="520" y2="50" className="stroke-line" strokeWidth="1.5" />

      {/* Platform between track 1 and track 2 */}
      <rect x="188" y="158" width="148" height="22" rx="2" className="fill-surface-sunken stroke-line" strokeWidth="1.5" />
      <text x="262" y="173" fontSize="10" letterSpacing="1.2" textAnchor="middle" className={LABEL}>
        BAHNSTEIG
      </text>

      {/* Signal box */}
      <rect x="54" y="250" width="62" height="38" rx="2" className="fill-surface-sunken stroke-ink" strokeWidth="1.5" />
      <text x="85" y="273" fontSize="11" letterSpacing="1.2" textAnchor="middle" className="fill-ink font-mono">
        STW
      </text>

      {/* Tracks 1–3 */}
      <path d="M24 200 H496" className={TRACK} strokeWidth="3" />
      <path d="M120 200 L168 140 H352 L400 200" className={TRACK} strokeWidth="3" />
      <path d="M220 200 L262 254 H432" className={TRACK} strokeWidth="3" />
      <path d="M432 244 V264" className={TRACK} strokeWidth="3" />

      {/* Track 4, under construction */}
      <path d="M352 140 L392 96 H478" className="fill-none stroke-accent" strokeWidth="3" strokeDasharray="8 7" />
      <text x="478" y="84" fontSize="11" letterSpacing="1.2" textAnchor="end" className="fill-accent-text font-mono">
        GL. 4 · IM BAU
      </text>

      {/* Turnouts */}
      {[
        { x: 120, y: 200, label: "W1", dy: 20 },
        { x: 220, y: 200, label: "W2", dy: 20 },
        { x: 400, y: 200, label: "W3", dy: 20 },
        { x: 352, y: 140, label: "W4", dy: -12 },
      ].map((turnout) => (
        <g key={turnout.label}>
          <circle cx={turnout.x} cy={turnout.y} r="4.5" className="fill-surface-raised stroke-ink" strokeWidth="2" />
          <text x={turnout.x} y={turnout.y + turnout.dy} fontSize="10" textAnchor="middle" className={LABEL}>
            {turnout.label}
          </text>
        </g>
      ))}

      {/* Signals: post, head, lamp */}
      {[
        { x: 72, lamp: "fill-success", label: "A" },
        { x: 452, lamp: "fill-danger", label: "F" },
      ].map((signal) => (
        <g key={signal.label}>
          <path d={`M${signal.x} 192 V172`} className={TRACK} strokeWidth="1.5" />
          <circle cx={signal.x} cy="164" r="8" className="fill-ink" />
          <circle cx={signal.x} cy="164" r="4" className={signal.lamp} />
          <text x={signal.x + 14} y="168" fontSize="11" className={LABEL}>
            {signal.label}
          </text>
        </g>
      ))}

      {/* Track numbers */}
      <text x="40" y="218" fontSize="11" className={LABEL}>
        GL. 1
      </text>
      <text x="196" y="130" fontSize="11" className={LABEL}>
        GL. 2
      </text>
      <text x="300" y="274" fontSize="11" className={LABEL}>
        GL. 3
      </text>

      {/* Legend */}
      <line x1="0" y1="304" x2="520" y2="304" className="stroke-line" strokeWidth="1.5" />
      <g fontSize="11" className={LABEL}>
        <circle cx="30" cy="322" r="4.5" className="fill-surface-raised stroke-ink" strokeWidth="2" />
        <text x="42" y="326">WEICHE</text>
        <circle cx="122" cy="322" r="6" className="fill-ink" />
        <text x="136" y="326">SIGNAL</text>
        <path d="M214 322 H246" className="fill-none stroke-accent" strokeWidth="3" strokeDasharray="8 7" />
        <text x="256" y="326">IN VORBEREITUNG</text>
      </g>
    </svg>
  );
}
