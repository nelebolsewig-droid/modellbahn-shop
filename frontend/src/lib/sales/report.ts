import type { ReportChannel, SaleChannel, SoldLineOut } from "@/lib/api/generated/model";

/**
 * The sales report (Verkäufe, ADR 0039): the spans to look at, the channels by name and
 * colour, and the sums by day and channel. Pure, so it is tested without the page.
 */

const SHOP_TIME_ZONE = "Europe/Berlin";

export const CHANNEL_ORDER: readonly ReportChannel[] = ["shop", "ebay", "fair", "store", "private", "other", "unknown"];

export const CHANNEL_LABELS: Readonly<Record<ReportChannel, string>> = {
  shop: "Onlineshop",
  ebay: "eBay",
  fair: "Messe",
  store: "Laden",
  private: "Privat",
  other: "Sonstiges",
  unknown: "Ohne Angabe",
};

/** Where a piece booked out as sold can have gone; the choice at Ausbuchen. */
export const SALE_CHANNELS: readonly SaleChannel[] = ["fair", "store", "private", "other"];

/**
 * One swatch per channel, from the adp palette: the fair in mandarin (what this page is
 * mostly opened for), online in espresso, the rest in terracotta and sand. Always shown
 * with the channel's name, never as colour alone.
 */
export const CHANNEL_SWATCHES: Readonly<Record<ReportChannel, string>> = {
  shop: "bg-ink",
  ebay: "bg-ink-tertiary",
  fair: "bg-action",
  store: "bg-highlight",
  private: "bg-line-control",
  other: "bg-line-strong",
  unknown: "stellwerk-hatch bg-sunken text-line-control",
};

export type Span = { start: string; end: string };
export type SpanKey = "today" | "yesterday" | "week" | "month" | "thisMonth" | "thisYear";

export const SPAN_LABELS: Readonly<Record<SpanKey, string>> = {
  today: "Heute",
  yesterday: "Gestern",
  week: "7 Tage",
  month: "30 Tage",
  thisMonth: "Dieser Monat",
  thisYear: "Dieses Jahr",
};

const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: SHOP_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });

/** The shop day (Europe/Berlin) of an instant, as YYYY-MM-DD. */
export function shopDay(instant: Date | string): string {
  return dayFormat.format(typeof instant === "string" ? new Date(instant) : instant);
}

/** YYYY-MM-DD plus or minus whole days, calendar arithmetic without time zones. */
export function addDays(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function spanFor(key: SpanKey, now: Date = new Date()): Span {
  const today = shopDay(now);
  switch (key) {
    case "today":
      return { start: today, end: today };
    case "yesterday": {
      const yesterday = addDays(today, -1);
      return { start: yesterday, end: yesterday };
    }
    case "week":
      return { start: addDays(today, -6), end: today };
    case "month":
      return { start: addDays(today, -29), end: today };
    case "thisMonth":
      return { start: `${today.slice(0, 8)}01`, end: today };
    case "thisYear":
      return { start: `${today.slice(0, 5)}01-01`, end: today };
  }
}

/** Every day of the span, the latest first. */
export function daysOf(span: Span): string[] {
  const days: string[] = [];
  for (let day = span.end; day >= span.start && days.length < 400; day = addDays(day, -1)) {
    days.push(day);
  }
  return days;
}

export type Tally = { cents: number; pieces: number; sales: number };

const EMPTY: Tally = { cents: 0, pieces: 0, sales: 0 };

function add(tally: Tally, line: SoldLineOut): Tally {
  return { cents: tally.cents + line.total_cents, pieces: tally.pieces + line.quantity, sales: tally.sales + 1 };
}

export function totals(lines: readonly SoldLineOut[]): Tally & { estimatedCents: number; estimatedPieces: number } {
  let tally = EMPTY;
  let estimatedCents = 0;
  let estimatedPieces = 0;
  for (const line of lines) {
    tally = add(tally, line);
    if (line.price_from_shop) {
      estimatedCents += line.total_cents;
      estimatedPieces += line.quantity;
    }
  }
  return { ...tally, estimatedCents, estimatedPieces };
}

export type ChannelShare = Tally & { channel: ReportChannel };

/** The channels that sold something, in their fixed order. */
export function byChannel(lines: readonly SoldLineOut[]): ChannelShare[] {
  const tallies = new Map<ReportChannel, Tally>();
  for (const line of lines) {
    tallies.set(line.channel, add(tallies.get(line.channel) ?? EMPTY, line));
  }
  return CHANNEL_ORDER.filter((channel) => tallies.has(channel)).map((channel) => ({
    channel,
    ...(tallies.get(channel) as Tally),
  }));
}

export type DayRow = Tally & { day: string; channels: ChannelShare[]; lines: SoldLineOut[] };

/** Every day of the span with its sums, the latest first; days without sales stay in (as 0). */
export function byDay(lines: readonly SoldLineOut[], span: Span): DayRow[] {
  const grouped = new Map<string, SoldLineOut[]>();
  for (const line of lines) {
    const day = shopDay(line.sold_at);
    grouped.set(day, [...(grouped.get(day) ?? []), line]);
  }
  return daysOf(span).map((day) => {
    const dayLines = grouped.get(day) ?? [];
    return { day, ...totals(dayLines), channels: byChannel(dayLines), lines: dayLines };
  });
}

/** The share of a part in a whole, in percent; 0 for an empty whole. */
export function share(part: number, whole: number): number {
  return whole > 0 ? (part / whole) * 100 : 0;
}

const weekdayFormat = new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", timeZone: "UTC" });
const longDayFormat = new Intl.DateTimeFormat("de-DE", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const timeFormat = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: SHOP_TIME_ZONE });
const shortDate = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** "Fr., 20.11." */
export function weekdayLabel(day: string): string {
  return weekdayFormat.format(new Date(`${day}T12:00:00Z`));
}

/** "Freitag, 20. November" */
export function longDayLabel(day: string): string {
  return longDayFormat.format(new Date(`${day}T12:00:00Z`));
}

/** "14:32" in shop time. */
export function timeLabel(instant: string): string {
  return timeFormat.format(new Date(instant));
}

/** "20. Nov. 2026" or "1. Nov. 2026 – 20. Nov. 2026". */
export function spanLabel(span: Span): string {
  const start = shortDate.format(new Date(`${span.start}T12:00:00Z`));
  if (span.start === span.end) {
    return start;
  }
  return `${start} – ${shortDate.format(new Date(`${span.end}T12:00:00Z`))}`;
}

export function piecesLabel(count: number): string {
  return count === 1 ? "1 Stück" : `${count.toLocaleString("de-DE")} Stück`;
}

export type MonthRow = Tally & { month: string; channels: ChannelShare[] };

/** Every month the span touches with its sums, the latest first: the view for long spans. */
export function byMonth(lines: readonly SoldLineOut[], span: Span): MonthRow[] {
  const grouped = new Map<string, SoldLineOut[]>();
  for (const line of lines) {
    const month = shopDay(line.sold_at).slice(0, 7);
    grouped.set(month, [...(grouped.get(month) ?? []), line]);
  }
  const months: string[] = [];
  for (let month = span.end.slice(0, 7); month >= span.start.slice(0, 7) && months.length < 24; ) {
    months.push(month);
    month = addDays(`${month}-01`, -1).slice(0, 7);
  }
  return months.map((month) => {
    const monthLines = grouped.get(month) ?? [];
    return { month, ...totals(monthLines), channels: byChannel(monthLines) };
  });
}

const monthFormat = new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric", timeZone: "UTC" });

/** "November 2026" */
export function monthLabel(month: string): string {
  return monthFormat.format(new Date(`${month}-15T12:00:00Z`));
}
