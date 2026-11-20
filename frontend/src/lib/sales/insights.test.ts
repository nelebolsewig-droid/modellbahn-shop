import { describe, expect, it } from "vitest";

import type { AdminFairOut, SoldLineOut } from "@/lib/api/generated/model";

import { fairResults, forecast, pace, piecesByKey, previousSpan, rank, stockChecks } from "./insights";

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
    variant_id: "adk-h0",
    product_name: "IFA ADK 70",
    product_slug: "ifa-adk-70",
    scale_code: "H0",
    variant_name: "H0 · Fertigmodell",
    ...overrides,
  };
}

function fair(overrides: Partial<AdminFairOut>): AdminFairOut {
  return {
    id: "kborn",
    name: "Modellbahnbörse Kühlungsborn",
    starts_on: "2026-11-20",
    ends_on: "2026-11-22",
    announced_at: null,
    booth: "",
    city: "Kühlungsborn",
    created_at: "2026-10-01T10:00:00Z",
    hours: "",
    note: "",
    postal_code: "18225",
    published: true,
    street: "",
    updated_at: "2026-10-01T10:00:00Z",
    venue: "",
    website_url: "",
    when: "20.–22. November 2026",
    ...overrides,
  };
}

const ADK_TT = { variant_id: "adk-tt", scale_code: "TT", title: "IFA ADK 70 · TT · Fertigmodell", variant_name: "TT · Fertigmodell" };
const EDK = {
  variant_id: "edk-h0",
  product_name: "EDK 6",
  product_slug: "edk-6",
  title: "EDK 6 · H0 · Bausatz",
  variant_name: "H0 · Bausatz",
  unit_price_cents: 2900,
  total_cents: 2900,
};

const LINES = [
  line({ key: "a" }),
  line({ key: "b", ...ADK_TT, unit_price_cents: 3000, total_cents: 3000 }),
  line({ key: "c", ...EDK, quantity: 2, total_cents: 5800 }),
  line({ key: "d", channel: "shop", kind: "order_line", unit_code: null, quantity: 2, total_cents: 7000 }),
];

describe("best sellers", () => {
  it("ranks models by money and shows their scales", () => {
    const rows = rank(LINES, "model");
    expect(rows.map((row) => row.label)).toEqual(["IFA ADK 70", "EDK 6"]);
    expect(rows[0]).toMatchObject({ pieces: 4, cents: 13500, averageCents: 3375, detail: "H0 3 · TT 1" });
    expect(rows[0]?.variantIds.sort()).toEqual(["adk-h0", "adk-tt"]);
  });

  it("ranks scales and counts their models", () => {
    const rows = rank(LINES, "scale");
    expect(rows.map((row) => [row.label, row.pieces, row.detail])).toEqual([
      ["H0", 5, "2 Modelle"],
      ["TT", 1, "1 Modell"],
    ]);
  });

  it("ranks variants on their own", () => {
    expect(rank(LINES, "variant").map((row) => row.key)).toEqual(["adk-h0", "edk-h0", "adk-tt"]);
  });

  it("counts pieces per key for the trend", () => {
    expect(piecesByKey(LINES, "model").get("ifa-adk-70")).toBe(4);
  });
});

describe("pace and forecast", () => {
  const now = new Date("2026-11-21T15:00:00Z"); // Saturday, the fair's second day

  it("takes the span just before as the comparison", () => {
    expect(previousSpan({ start: "2026-11-14", end: "2026-11-20" })).toEqual({ start: "2026-11-07", end: "2026-11-13" });
  });

  it("counts only the days that have begun", () => {
    const result = pace(LINES, { start: "2026-11-20", end: "2026-11-30" }, now);
    expect(result.days).toBe(2);
    expect(result.centsPerDay).toBe(9650);
  });

  it("projects a running fair to its last day", () => {
    const result = forecast(LINES, { start: "2026-11-20", end: "2026-11-21" }, fair({}), now);
    expect(result).toMatchObject({ kind: "fair", dayNumber: 2, daysTotal: 3, daysLeft: 1 });
    // 193 € in two days → 96,50 € more on Sunday.
    expect(result?.cents).toBe(28950);
    expect(result?.pieces).toBe(9);
  });

  it("looks 30 days ahead after a week of figures, and not before", () => {
    const week = { start: "2026-11-15", end: "2026-11-21" };
    expect(forecast(LINES, week, null, now)).toMatchObject({ kind: "ahead", daysLeft: 30, cents: Math.round((19300 / 7) * 30) });
    expect(forecast(LINES, { start: "2026-11-19", end: "2026-11-21" }, null, now)).toBeNull();
    expect(forecast(LINES, { start: "2026-11-01", end: "2026-11-10" }, null, now)).toBeNull();
  });
});

describe("stock checks", () => {
  it("warns when the pace wants more than the shelf holds", () => {
    const rows = rank(LINES, "variant");
    const free = new Map([
      ["adk-h0", 1],
      ["edk-h0", 2],
      ["adk-tt", 9],
    ]);
    const checks = stockChecks(rows, free, 2, 1);
    expect(checks.map((check) => [check.key, check.wanted, check.free, check.tone])).toEqual([
      ["adk-h0", 2, 1, "short"],
      ["edk-h0", 1, 2, "ok"],
      ["adk-tt", 1, 9, "ok"],
    ]);
    expect(checks[0]?.lastsDays).toBe(0);
    expect(checks[2]?.lastsDays).toBe(18);
  });
});

describe("fairs compared", () => {
  it("sums each fair's own days and channel, the latest first", () => {
    const now = new Date("2026-11-21T15:00:00Z");
    const fairs = [fair({}), fair({ id: "leipzig", name: "Leipzig", starts_on: "2026-10-03", ends_on: "2026-10-04" }), fair({ id: "later", starts_on: "2026-12-05", ends_on: "2026-12-06" })];
    const lines = [...LINES, line({ key: "e", sold_at: "2026-10-03T11:00:00Z" }), line({ key: "f", sold_at: "2026-10-12T11:00:00Z" })];
    const results = fairResults(lines, fairs, now);
    expect(results.map((result) => [result.fair.id, result.days, result.pieces, result.cents, result.running])).toEqual([
      ["kborn", 2, 4, 12300, true],
      ["leipzig", 2, 1, 3500, false],
    ]);
    expect(results[0]?.top?.label).toBe("IFA ADK 70");
  });
});
