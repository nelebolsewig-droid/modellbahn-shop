import { describe, expect, it } from "vitest";

import { formatEventTime, formatLongDate, formatWeekdayDate, greetingFor } from "./format";

describe("formatEventTime", () => {
  const now = new Date("2026-10-22T15:00:00Z");

  it("shows only the time for events of today, in German time", () => {
    // 12:32 UTC is 14:32 in Berlin (summer time until 25 October 2026).
    expect(formatEventTime(new Date("2026-10-22T12:32:05Z"), now)).toBe("14:32:05");
  });

  it("adds the date for other days", () => {
    expect(formatEventTime(new Date("2026-10-21T12:32:05Z"), now)).toBe("21.10.2026, 14:32:05");
  });

  it("decides 'today' by the German calendar day, not by UTC", () => {
    // 22:30 UTC on the 21st is already 00:30 on the 22nd in Berlin.
    expect(formatEventTime(new Date("2026-10-21T22:30:00Z"), now)).toBe("00:30:00");
  });
});

describe("dates", () => {
  it("formats long dates in German", () => {
    expect(formatLongDate(new Date("2026-10-22T08:00:00Z"))).toBe("22. Oktober 2026");
    expect(formatWeekdayDate(new Date("2026-10-22T08:00:00Z"))).toBe("Donnerstag, 22. Oktober");
  });
});

describe("greetingFor", () => {
  it.each([
    ["2026-10-22T05:30:00Z", "Guten Morgen"], // 07:30 in Berlin
    ["2026-10-22T10:00:00Z", "Guten Tag"], // 12:00
    ["2026-10-22T17:00:00Z", "Guten Abend"], // 19:00
    ["2026-10-22T00:30:00Z", "Guten Abend"], // 02:30
  ])("greets at %s with %s", (iso, greeting) => {
    expect(greetingFor(new Date(iso))).toBe(greeting);
  });
});
