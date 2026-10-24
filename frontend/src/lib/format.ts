/*
 * Dates and times as German readers expect them. The shop and its workshop are in
 * Germany, so times are shown in German time for everybody: an event at 14:32 in the
 * workshop reads 14:32 on every screen.
 */

const TIME_ZONE = "Europe/Berlin";
const LOCALE = "de-DE";

const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const calendarDayFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const longDateFormat = new Intl.DateTimeFormat(LOCALE, { timeZone: TIME_ZONE, dateStyle: "long" });

const weekdayDateFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
});

const hourFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "numeric",
  hourCycle: "h23",
});

function isSameDay(a: Date, b: Date): boolean {
  return calendarDayFormat.format(a) === calendarDayFormat.format(b);
}

/** "14:32:05" for today, "21.10.2026, 14:32:05" for any other day. */
export function formatEventTime(date: Date, now: Date = new Date()): string {
  return isSameDay(date, now) ? timeFormat.format(date) : dateTimeFormat.format(date);
}

/** "14:32:05" */
export function formatTime(date: Date): string {
  return timeFormat.format(date);
}

/** "22. Oktober 2026" */
export function formatLongDate(date: Date): string {
  return longDateFormat.format(date);
}

/** "Donnerstag, 22. Oktober" */
export function formatWeekdayDate(date: Date): string {
  return weekdayDateFormat.format(date);
}

function hourInGermany(date: Date): number {
  // format() would give "14 Uhr"; the parts hold the bare number.
  const hour = hourFormat.formatToParts(date).find((part) => part.type === "hour");
  return Number(hour?.value);
}

/** "Guten Morgen", "Guten Tag" or "Guten Abend", by the time of day in Germany. */
export function greetingFor(date: Date): string {
  const hour = hourInGermany(date);
  if (hour >= 5 && hour < 11) {
    return "Guten Morgen";
  }
  if (hour >= 11 && hour < 18) {
    return "Guten Tag";
  }
  return "Guten Abend";
}
