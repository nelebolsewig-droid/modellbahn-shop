import type { AdminFairOut, SoldLineOut } from "@/lib/api/generated/model";

import { addDays, daysOf, shopDay, totals, type Span } from "./report";

/**
 * The evaluation of the sales (Auswertung, ADR 0042): what sells best by model, scale or
 * variant, how fairs compare, and where the current pace leads. Pure, so it is tested
 * without the page; the page only draws it.
 */

export type RankBy = "model" | "scale" | "variant";

export const RANK_LABELS: Readonly<Record<RankBy, string>> = {
  model: "Modell",
  scale: "Maßstab",
  variant: "Ausführung",
};

export type RankRow = {
  key: string;
  label: string;
  /** The second line: the scales of a model ("H0 4 · TT 2"), the model of a variant. */
  detail: string;
  pieces: number;
  cents: number;
  /** Average gross price of one piece. */
  averageCents: number;
  /** Variants sold under this row: the stock check looks at them. */
  variantIds: string[];
};

function keyOf(line: SoldLineOut, by: RankBy): string {
  switch (by) {
    case "model":
      return line.product_slug || line.product_name || line.title;
    case "scale":
      return line.scale_code || "–";
    case "variant":
      return line.variant_id ?? line.title;
  }
}

function labelOf(line: SoldLineOut, by: RankBy): string {
  switch (by) {
    case "model":
      return line.product_name || line.title;
    case "scale":
      return line.scale_code || "Ohne Maßstab";
    case "variant":
      return line.title;
  }
}

/** Pieces per part, the most first: "H0 4 · TT 2". */
function breakdown(parts: Map<string, number>): string {
  return [...parts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "de"))
    .map(([name, pieces]) => `${name} ${pieces}`)
    .join(" · ");
}

/** The best sellers, by money first (what the stand earns), then by pieces. */
export function rank(lines: readonly SoldLineOut[], by: RankBy): RankRow[] {
  type Acc = { label: string; pieces: number; cents: number; parts: Map<string, number>; variants: Set<string> };
  const rows = new Map<string, Acc>();
  for (const line of lines) {
    const key = keyOf(line, by);
    const acc = rows.get(key) ?? { label: labelOf(line, by), pieces: 0, cents: 0, parts: new Map(), variants: new Set() };
    acc.pieces += line.quantity;
    acc.cents += line.total_cents;
    const part = by === "model" ? line.scale_code || "–" : by === "scale" ? line.product_name || line.title : "";
    if (part) {
      acc.parts.set(part, (acc.parts.get(part) ?? 0) + line.quantity);
    }
    if (line.variant_id) {
      acc.variants.add(line.variant_id);
    }
    rows.set(key, acc);
  }
  return [...rows.entries()]
    .map(([key, acc]) => ({
      key,
      label: acc.label,
      detail: by === "scale" ? `${acc.parts.size} ${acc.parts.size === 1 ? "Modell" : "Modelle"}` : breakdown(acc.parts),
      pieces: acc.pieces,
      cents: acc.cents,
      averageCents: acc.pieces > 0 ? Math.round(acc.cents / acc.pieces) : 0,
      variantIds: [...acc.variants],
    }))
    .sort((a, b) => b.cents - a.cents || b.pieces - a.pieces || a.label.localeCompare(b.label, "de"));
}

/** The span just before, as long as this one: what a trend compares with. */
export function previousSpan(span: Span): Span {
  const days = daysOf(span).length;
  return { start: addDays(span.start, -days), end: addDays(span.start, -1) };
}

/** Pieces sold per key in a period, for the trend next to each best seller. */
export function piecesByKey(lines: readonly SoldLineOut[], by: RankBy): Map<string, number> {
  const pieces = new Map<string, number>();
  for (const line of lines) {
    const key = keyOf(line, by);
    pieces.set(key, (pieces.get(key) ?? 0) + line.quantity);
  }
  return pieces;
}

/* --- Pace and forecast ------------------------------------------------------------- */

export type Pace = {
  /** Days the figures cover so far (today counts in full). */
  days: number;
  centsPerDay: number;
  piecesPerDay: number;
};

/** What the span sold per day, counting only the days that have begun. */
export function pace(lines: readonly SoldLineOut[], span: Span, now: Date = new Date()): Pace {
  const today = shopDay(now);
  const end = span.end < today ? span.end : today;
  const days = span.start > end ? 0 : daysOf({ start: span.start, end }).length;
  const sum = totals(lines);
  return {
    days,
    centsPerDay: days > 0 ? sum.cents / days : 0,
    piecesPerDay: days > 0 ? sum.pieces / days : 0,
  };
}

export type Forecast = {
  /** What the forecast reaches to: the fair's last day, or a number of days ahead. */
  kind: "fair" | "ahead";
  /** Days still to come (the fair's remaining days, or the horizon). */
  daysLeft: number;
  /** The fair's days, all of them; 0 for "ahead". */
  daysTotal: number;
  /** Today is which day of the fair (1 = the first); 0 for "ahead". */
  dayNumber: number;
  /** Sold so far plus what the pace adds, for a fair; only what the pace adds, ahead. */
  cents: number;
  pieces: number;
  pace: Pace;
};

export const AHEAD_DAYS = 30;

/**
 * Where the pace leads. A running fair: its total by the last day, at the pace of its
 * days so far (today counted in full, so early in the day the forecast is cautious).
 * Otherwise, with at least a week of figures: the next 30 days.
 */
export function forecast(lines: readonly SoldLineOut[], span: Span, fair: AdminFairOut | null, now: Date = new Date()): Forecast | null {
  const today = shopDay(now);
  if (fair && fair.starts_on <= today && today <= fair.ends_on) {
    const total = daysOf({ start: fair.starts_on, end: fair.ends_on }).length;
    const sold = totals(lines);
    const current = pace(lines, { start: fair.starts_on, end: fair.ends_on }, now);
    const left = total - current.days;
    return {
      kind: "fair",
      daysLeft: left,
      daysTotal: total,
      dayNumber: current.days,
      cents: Math.round(sold.cents + current.centsPerDay * left),
      pieces: Math.round(sold.pieces + current.piecesPerDay * left),
      pace: current,
    };
  }
  const current = pace(lines, span, now);
  if (span.end < today || current.days < 7 || lines.length === 0) {
    return null;
  }
  return {
    kind: "ahead",
    daysLeft: AHEAD_DAYS,
    daysTotal: 0,
    dayNumber: 0,
    cents: Math.round(current.centsPerDay * AHEAD_DAYS),
    pieces: Math.round(current.piecesPerDay * AHEAD_DAYS),
    pace: current,
  };
}

export type StockCheck = RankRow & {
  free: number;
  /** Pieces the pace still asks for in the forecast's days. */
  wanted: number;
  /** Days the free pieces last at this pace; null when none were sold per day. */
  lastsDays: number | null;
  tone: "ok" | "tight" | "short";
};

/**
 * The best sellers against the free stock: do the pieces last until the fair ends (or the
 * next 30 days)? "short" when the pace wants more than there is, "tight" when it wants
 * more than two thirds.
 */
export function stockChecks(
  rows: readonly RankRow[],
  free: ReadonlyMap<string, number>,
  days: number,
  forecastDaysLeft: number,
  limit = 5,
): StockCheck[] {
  return rows.slice(0, limit).map((row) => {
    const pieces = row.variantIds.reduce((sum, id) => sum + (free.get(id) ?? 0), 0);
    const perDay = days > 0 ? row.pieces / days : 0;
    const wanted = Math.ceil(perDay * forecastDaysLeft);
    const tone = wanted > pieces ? "short" : wanted > (pieces * 2) / 3 ? "tight" : "ok";
    return { ...row, free: pieces, wanted, lastsDays: perDay > 0 ? Math.floor(pieces / perDay) : null, tone };
  });
}

/* --- Fairs compared ---------------------------------------------------------------- */

export type FairResult = {
  fair: AdminFairOut;
  /** Days of the fair that have begun. */
  days: number;
  pieces: number;
  cents: number;
  centsPerDay: number;
  top: RankRow | null;
  running: boolean;
};

/**
 * Every fair of the list that has begun, with what was sold there: pieces booked out with
 * the channel Messe on its days. The latest first.
 */
export function fairResults(lines: readonly SoldLineOut[], fairs: readonly AdminFairOut[], now: Date = new Date()): FairResult[] {
  const today = shopDay(now);
  return fairs
    .filter((fair) => fair.starts_on <= today)
    .map((fair) => {
      const end = fair.ends_on < today ? fair.ends_on : today;
      const sold = lines.filter((line) => {
        if (line.channel !== "fair") {
          return false;
        }
        const day = shopDay(line.sold_at);
        return fair.starts_on <= day && day <= end;
      });
      const sum = totals(sold);
      const days = daysOf({ start: fair.starts_on, end }).length;
      return {
        fair,
        days,
        pieces: sum.pieces,
        cents: sum.cents,
        centsPerDay: days > 0 ? Math.round(sum.cents / days) : 0,
        top: rank(sold, "model")[0] ?? null,
        running: fair.ends_on >= today,
      };
    })
    .sort((a, b) => b.fair.starts_on.localeCompare(a.fair.starts_on));
}
