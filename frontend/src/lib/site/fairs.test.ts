import { describe, expect, it } from "vitest";

import { countdown, dateBlock, daysBetween, place, routeUrl, todayInGermany, webcalUrl } from "./fairs";

const DASH = "–";

describe("dateBlock", () => {
  it("names one day with its weekday", () => {
    expect(dateBlock({ starts_on: "2026-11-07", ends_on: "2026-11-07" })).toEqual({
      days: "7.",
      months: "Nov 2026",
      weekdays: "Sa",
      long: false,
    });
  });

  it("names the month once for days within it", () => {
    expect(dateBlock({ starts_on: "2026-11-20", ends_on: "2026-11-22" })).toEqual({
      days: `20.${DASH}22.`,
      months: "Nov 2026",
      weekdays: `Fr${DASH}So`,
      long: false,
    });
  });

  it("writes day and month across a month's end", () => {
    const block = dateBlock({ starts_on: "2026-10-30", ends_on: "2026-11-01" });
    expect(block.days).toBe(`30.10.${DASH}1.11.`);
    expect(block.months).toBe(`Okt${DASH}Nov 2026`);
    expect(block.long).toBe(true);
  });

  it("names both years across New Year", () => {
    expect(dateBlock({ starts_on: "2026-12-30", ends_on: "2027-01-02" }).months).toBe(
      `Dez 2026${DASH}Jan 2027`,
    );
  });
});

describe("countdown", () => {
  const leipzig = { starts_on: "2026-10-02", ends_on: "2026-10-04" };

  it.each([
    ["2026-10-03", "Heute geöffnet"],
    ["2026-10-01", "Morgen"],
    ["2026-09-23", "In 9 Tagen"],
    ["2026-09-04", "In 4 Wochen"],
    ["2026-07-01", null],
    ["2026-10-05", null],
  ])("on %s says %s", (today, text) => {
    expect(countdown(leipzig, today)).toBe(text);
  });
});

describe("days", () => {
  it("counts calendar days, unmoved by summer time", () => {
    expect(daysBetween("2026-10-24", "2026-10-26")).toBe(2);
    expect(daysBetween("2026-10-26", "2026-10-24")).toBe(-2);
  });

  it("takes today from German time", () => {
    // 23:30 UTC on 31 October is already 1 November in Germany (CET, UTC+1).
    expect(todayInGermany(new Date("2026-10-31T23:30:00Z"))).toBe("2026-11-01");
  });
});

describe("where", () => {
  const dresden = { venue: "JohannStadthalle", street: "Holbeinstraße 68", postal_code: "01307", city: "Dresden" };

  it("leaves out what is unknown", () => {
    expect(place(dresden)).toBe("JohannStadthalle, Holbeinstraße 68, 01307 Dresden");
    expect(place({ venue: "Hotel Aquamarin", street: "", postal_code: "", city: "Kühlungsborn" })).toBe(
      "Hotel Aquamarin, Kühlungsborn",
    );
  });

  it("looks the address up on OpenStreetMap", () => {
    expect(routeUrl(dresden)).toBe(
      "https://www.openstreetmap.org/search?query=Holbeinstra%C3%9Fe%2068%2C%2001307%20Dresden",
    );
  });

  it("subscribes to the feed with webcal", () => {
    expect(webcalUrl("https://adp-modelle.de")).toBe("webcal://adp-modelle.de/api/v1/store/fairs/calendar.ics");
  });
});
