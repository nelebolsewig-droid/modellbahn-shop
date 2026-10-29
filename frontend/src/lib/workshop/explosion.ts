/**
 * The exploded view of a model (ADR 0016): which parts it has, how far each moves apart,
 * and how scrolling drives the explosion. Pure data and arithmetic, no three.js, so the
 * page and its tests need no WebGL.
 */

/** A simple solid in millimetres of the model (x along the length, y up, z across). */
export type Solid =
  | { kind: "box"; size: readonly [number, number, number]; at: readonly [number, number, number] }
  | {
      kind: "cylinder";
      radius: number;
      length: number;
      axis: "x" | "y" | "z";
      at: readonly [number, number, number];
      segments?: number;
    };

/** Solids that move together, along `direction` by `distance` mm when fully exploded. */
export type Piece = {
  solids: readonly Solid[];
  direction: readonly [number, number, number];
  distance: number;
};

/** A position of the parts list. */
export type ExplosionPart = {
  position: number;
  name: string;
  /** How many printed parts the position has. */
  count: number;
  printMinutes: number;
  /** When it comes off: 0 first. */
  order: number;
  pieces: readonly Piece[];
};

export type ExplosionModel = {
  name: string;
  scale: string;
  /** Made up to show the idea; the page says so until a real model replaces it. */
  placeholder: boolean;
  /** Finishing by hand after printing: removing supports, sanding, painting, assembly. */
  handworkMinutes: number;
  parts: readonly ExplosionPart[];
};

export type ExplosionTotals = { parts: number; printMinutes: number; handworkMinutes: number };

export function totalsOf(model: ExplosionModel): ExplosionTotals {
  return {
    parts: model.parts.reduce((sum, part) => sum + part.count, 0),
    printMinutes: model.parts.reduce((sum, part) => sum + part.printMinutes, 0),
    handworkMinutes: model.handworkMinutes,
  };
}

/** "2 h 40", "4 h", "50 min". */
export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
}

/** Whole hours for the big figures, rounded. */
export function hoursOf(minutes: number): number {
  return Math.round(minutes / 60);
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));

function smoothstep(from: number, to: number, value: number): number {
  const t = clamp((value - from) / (to - from));
  return t * t * (3 - 2 * t);
}

/** The process step the page shows: 0 take apart, 1 print, 2 put together. */
export type Phase = 0 | 1 | 2;

/**
 * How far the model is taken apart (0 to 1) at a point of the scroll track (0 to 1):
 * it comes apart, holds while the parts print, and goes back together at the end.
 */
export function explosionAt(progress: number): number {
  return smoothstep(0.08, 0.42, progress) * (1 - smoothstep(0.7, 0.94, progress));
}

export function phaseAt(progress: number): Phase {
  if (progress < 0.42) return 0;
  if (progress < 0.7) return 1;
  return 2;
}

/** The share of the explosion a part has made; parts that come off first move first. */
export function partShare(explosion: number, order: number, lastOrder: number): number {
  const delay = (order / (lastOrder + 1)) * 0.45;
  const local = clamp((explosion - delay) / (1 - delay));
  return 1 - Math.pow(1 - local, 3);
}

/** Opacity of the position balloons: they appear once the parts have moved apart. */
export function balloonOpacity(explosion: number): number {
  return smoothstep(0.55, 0.9, explosion);
}
