/*
 * Fairs as the shop shows them. The API sends calendar days ("2026-11-20") and the
 * dates in German words (`when`); these helpers lay them out for the timeline and
 * say how far away a fair is. Calendar days have no time zone: they are read as UTC
 * dates so that no browser moves a fair to the day before.
 */

import { getGetFairCalendarUrl, getGetFairEventUrl } from "@/lib/api/generated/store-site/store-site";

type FairDates = { starts_on: string; ends_on: string };

type FairPlace = { venue: string; street: string; postal_code: string; city: string };

const MONTHS = ["Jan", "Feb", "März", "Apr", "Mai", "Juni", "Juli", "Aug", "Sep", "Okt", "Nov", "Dez"] as const;
const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"] as const;
const DAY_MS = 86_400_000;
const EN_DASH = "–";

const berlinDay = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Berlin",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function parseDay(iso: string): Date {
  const [year = 0, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

/** Today in the workshop's time zone, as the API writes days: "2026-10-28". */
export function todayInGermany(now: Date = new Date()): string {
  return berlinDay.format(now);
}

/** Whole days from `from` to `to` (both "YYYY-MM-DD"); negative when `to` lies before. */
export function daysBetween(from: string, to: string): number {
  return Math.round((parseDay(to).getTime() - parseDay(from).getTime()) / DAY_MS);
}

export type DateBlock = {
  /** "7.", "20.–22." or across months "30.10.–1.11." */
  days: string;
  /** "Nov 2026", "Okt–Nov 2026" or "Dez 2026–Jan 2027" */
  months: string;
  /** "Sa", "Fr–So" */
  weekdays: string;
  /** The days are long (across months) and need a smaller type size. */
  long: boolean;
};

/** The date as the big block on a fair's card. */
export function dateBlock({ starts_on, ends_on }: FairDates): DateBlock {
  const start = parseDay(starts_on);
  const end = parseDay(ends_on);
  const monthOf = (date: Date) => MONTHS[date.getUTCMonth()] ?? "";
  const weekdayOf = (date: Date) => WEEKDAYS[date.getUTCDay()] ?? "";
  const sameDay = starts_on === ends_on;
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear();
  const sameMonth = sameYear && start.getUTCMonth() === end.getUTCMonth();

  let days: string;
  if (sameDay) {
    days = `${start.getUTCDate()}.`;
  } else if (sameMonth) {
    days = `${start.getUTCDate()}.${EN_DASH}${end.getUTCDate()}.`;
  } else {
    const short = (date: Date) => `${date.getUTCDate()}.${date.getUTCMonth() + 1}.`;
    days = `${short(start)}${EN_DASH}${short(end)}`;
  }

  let months: string;
  if (sameMonth) {
    months = `${monthOf(start)} ${start.getUTCFullYear()}`;
  } else if (sameYear) {
    months = `${monthOf(start)}${EN_DASH}${monthOf(end)} ${end.getUTCFullYear()}`;
  } else {
    months = `${monthOf(start)} ${start.getUTCFullYear()}${EN_DASH}${monthOf(end)} ${end.getUTCFullYear()}`;
  }

  const weekdays = sameDay ? weekdayOf(start) : `${weekdayOf(start)}${EN_DASH}${weekdayOf(end)}`;
  return { days, months, weekdays, long: !sameMonth };
}

/**
 * How far away a fair is, in words: "Heute geöffnet", "Morgen", "In 9 Tagen",
 * "In 5 Wochen"; null when it is further than that or over.
 */
export function countdown({ starts_on, ends_on }: FairDates, today: string): string | null {
  if (daysBetween(today, ends_on) < 0) {
    return null;
  }
  const until = daysBetween(today, starts_on);
  if (until <= 0) {
    return "Heute geöffnet";
  }
  if (until === 1) {
    return "Morgen";
  }
  if (until < 14) {
    return `In ${until} Tagen`;
  }
  if (until < 63) {
    return `In ${Math.floor(until / 7)} Wochen`;
  }
  return null;
}

/** Postal code and city: "01307 Dresden". */
export function town(fair: FairPlace): string {
  return [fair.postal_code, fair.city].filter(Boolean).join(" ");
}

/** Venue, street and town, as far as known: "JohannStadthalle, Holbeinstraße 68, 01307 Dresden". */
export function place(fair: FairPlace): string {
  return [fair.venue, fair.street, town(fair)].filter(Boolean).join(", ");
}

/** A route to the venue on OpenStreetMap: no tracking, no consent banner. */
export function routeUrl(fair: FairPlace): string {
  const query = [fair.street, town(fair)].filter(Boolean).join(", ") || place(fair);
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(query)}`;
}

/** One fair as an .ics file. */
export function fairEventUrl(fairId: string): string {
  return getGetFairEventUrl(fairId);
}

/** All published fairs as a calendar feed. */
export const FAIR_FEED_PATH = getGetFairCalendarUrl();

/** The feed as a calendar subscription: calendar apps open webcal:// links themselves. */
export function webcalUrl(origin: string): string {
  return `${origin.replace(/^https?:/, "webcal:")}${FAIR_FEED_PATH}`;
}

/** Opening hours, one entry per line. */
export function hourLines(hours: string): string[] {
  return hours
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
