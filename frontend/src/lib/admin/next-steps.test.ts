import { describe, expect, it } from "vitest";

import type { HallOut, OrderSummaryOut, PrinterDeskOut, PrintJobOut, ToMakeOut } from "@/lib/api/generated/model";

import { nextSteps } from "./next-steps";

const NOW = new Date("2026-11-18T12:00:00Z");

function order(number: string, placedAt: string, overrides: Partial<OrderSummaryOut> = {}): OrderSummaryOut {
  return {
    id: `id-${number}`,
    number,
    placed_at: placedAt,
    channel: "shop",
    first_line_title: "ADK 80 · H0",
    guest: true,
    item_count: 1,
    recipient: "Erika Muster",
    status: "paid",
    total_cents: 8590,
    ...overrides,
  };
}

function job(number: number, overrides: Partial<PrintJobOut> = {}): PrintJobOut {
  return {
    id: `job-${number}`,
    number,
    created_at: "2026-11-18T08:00:00Z",
    expected_end_at: null,
    failure_reason: "",
    finished_at: null,
    lines: [{ part: { id: "p", number: "ADK-AUSLEGER-H0", name: "Ausleger" }, quantity: 4 } as unknown as PrintJobOut["lines"][number]],
    note: "",
    part_count: 4,
    planned_minutes: 60,
    printed_at: null,
    printer: { id: "d1", code: "D01", name: "Saturn" } as PrintJobOut["printer"],
    started_at: null,
    status: "queued" as PrintJobOut["status"],
    technology: "resin",
    ...overrides,
  };
}

function printer(code: string, overrides: Partial<PrinterDeskOut> = {}): PrinterDeskOut {
  return {
    id: `id-${code}`,
    code,
    name: code,
    model: "Saturn 4",
    notes: "",
    build_x_mm: null,
    build_y_mm: null,
    build_z_mm: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    printing: null,
    queue: [],
    status: "in_service",
    status_changed_at: "2026-11-16T12:00:00Z",
    status_note: "",
    technology: "resin",
    ...overrides,
  };
}

function hall(printers: PrinterDeskOut[], post: PrintJobOut[] = []): HallOut {
  return { printers, post_processing: post, counts: {} as HallOut["counts"] };
}

describe("nextSteps", () => {
  it("is empty on a quiet day", () => {
    expect(nextSteps({ ready: [], unpaid: [], hall: hall([]), toMake: [], now: NOW })).toEqual([]);
  });

  it("orders the work as the workshop does it", () => {
    const steps = nextSteps({
      ready: [order("MB-2026-00004", "2026-11-18T09:00:00Z"), order("MB-2026-00002", "2026-11-17T09:00:00Z")],
      unpaid: [order("MB-2026-00001", "2026-11-13T09:00:00Z", { status: "pending_payment" })],
      hall: hall(
        [
          printer("D01", { printing: job(17, { status: "printing" as PrintJobOut["status"], started_at: "2026-11-18T10:00:00Z" }) }),
          printer("D02", { status: "defective", status_note: "FEP gerissen" }),
          printer("D03", { queue: [job(18), job(19)] }),
        ],
        [job(15, { status: "post_processing" as PrintJobOut["status"] })],
      ),
      toMake: [
        {
          variant_id: "v1",
          product_id: "m1",
          model: "IFA ADK 80",
          finish: "Fertigmodell",
          quantity: 2,
          sku: "MB-000002-H0-F",
          oldest_at: "2026-11-17T09:00:00Z",
          orders: [{ number: "MB-2026-00003" } as ToMakeOut["orders"][number]],
        },
      ],
      now: NOW,
    });
    expect(steps.map((step) => step.title)).toEqual([
      "D02 ist defekt",
      "D01: Druck 17 ist fertig gedruckt",
      "Druck 15: gute Teile melden",
      "MB-2026-00002 packen",
      "MB-2026-00004 packen",
      "D03 ist frei",
      "2 × IFA ADK 80",
      "MB-2026-00001 wartet seit 5 Tagen aufs Geld",
    ]);
    expect(steps[0]?.detail).toBe("seit 2 Tagen · FEP gerissen");
    expect(steps[5]?.detail).toBe("2 Platten warten · als Nächstes Druck 18");
  });

  it("leaves a plate on the printer until its time is up", () => {
    const steps = nextSteps({
      ready: [],
      unpaid: [],
      hall: hall([printer("D01", { printing: job(17, { status: "printing" as PrintJobOut["status"], started_at: "2026-11-18T11:30:00Z" }) })]),
      toMake: null,
      now: NOW,
    });
    expect(steps).toEqual([]);
  });

  it("names unpaid orders only after a few days", () => {
    const steps = nextSteps({
      ready: [],
      unpaid: [order("MB-2026-00009", "2026-11-17T09:00:00Z", { status: "pending_payment" })],
      hall: undefined,
      toMake: null,
      now: NOW,
    });
    expect(steps).toEqual([]);
  });
});
