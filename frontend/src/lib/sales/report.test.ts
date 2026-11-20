import { describe, expect, it } from "vitest";

import type { SoldLineOut } from "@/lib/api/generated/model";

import { addDays, byChannel, byDay, daysOf, shopDay, spanFor, totals } from "./report";

function line(overrides: Partial<SoldLineOut>): SoldLineOut {
  return {
    kind: "piece",
    key: "7KQ2X9F4MZ",
    channel: "fair",
    sold_at: "2026-11-20T10:00:00Z",
    title: "IFA ADK 70 · H0 · Fertigmodell",
    sku: "ADK-H0-F",
    quantity: 1,
    unit_price_cents: 3500,
    total_cents: 3500,
    price_from_shop: false,
    order_id: null,
    order_number: null,
    unit_code: "7KQ2X9F4MZ",
    note: "",
    staff_name: "Johann",
    variant_id: "v-adk-h0-f",
    product_name: "IFA ADK 70",
    product_slug: "ifa-adk-70",
    scale_code: "H0",
    variant_name: "H0 · Fertigmodell",
    ...overrides,
  };
}

describe("shop days", () => {
  it("counts a sale late in the evening to that evening in Germany", () => {
    // 23:30 in Berlin is still the 20th, although it is the 20th 22:30 UTC.
    expect(shopDay("2026-11-20T22:30:00Z")).toBe("2026-11-20");
    expect(shopDay("2026-11-20T23:30:00Z")).toBe("2026-11-21");
  });

  it("builds spans and walks the days backwards", () => {
    const now = new Date("2026-11-20T09:00:00Z");
    expect(spanFor("today", now)).toEqual({ start: "2026-11-20", end: "2026-11-20" });
    expect(spanFor("week", now)).toEqual({ start: "2026-11-14", end: "2026-11-20" });
    expect(spanFor("thisMonth", now)).toEqual({ start: "2026-11-01", end: "2026-11-20" });
    expect(spanFor("thisYear", now).start).toBe("2026-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(daysOf({ start: "2026-11-18", end: "2026-11-20" })).toEqual(["2026-11-20", "2026-11-19", "2026-11-18"]);
  });
});

describe("sums", () => {
  const lines = [
    line({ key: "A", total_cents: 3500 }),
    line({ key: "B", price_from_shop: true, channel: "unknown", total_cents: 4990, unit_price_cents: 4990 }),
    line({ key: "C", kind: "order_line", channel: "shop", quantity: 2, unit_price_cents: 4990, total_cents: 9980, sold_at: "2026-11-19T08:00:00Z" }),
  ];

  it("adds up money, pieces and what is only estimated at the shop price", () => {
    expect(totals(lines)).toEqual({ cents: 18470, pieces: 4, sales: 3, estimatedCents: 4990, estimatedPieces: 1 });
  });

  it("lists the channels in their fixed order", () => {
    expect(byChannel(lines).map((row) => [row.channel, row.cents])).toEqual([
      ["shop", 9980],
      ["fair", 3500],
      ["unknown", 4990],
    ]);
  });

  it("keeps every day of the span, the empty ones at zero", () => {
    const days = byDay(lines, { start: "2026-11-18", end: "2026-11-20" });
    expect(days.map((day) => [day.day, day.cents, day.lines.length])).toEqual([
      ["2026-11-20", 8490, 2],
      ["2026-11-19", 9980, 1],
      ["2026-11-18", 0, 0],
    ]);
  });
});

describe("months", () => {
  it("covers every month of a long span", async () => {
    const { byMonth } = await import("./report");
    const rows = byMonth([line({ sold_at: "2026-10-03T10:00:00Z" })], { start: "2026-09-15", end: "2026-11-20" });
    expect(rows.map((row) => [row.month, row.cents])).toEqual([
      ["2026-11", 0],
      ["2026-10", 3500],
      ["2026-09", 0],
    ]);
  });
});
