import { describe, expect, it } from "vitest";

import type { PrinterDeskOut, PrintJobOut } from "@/lib/api/generated/model";

import { deskState, estimateMinutes, formatMinutes, jobTitle, plateProgress, plateSummary, sinceText } from "./hall";

function job(overrides: Partial<PrintJobOut> = {}): PrintJobOut {
  return {
    id: "j1",
    number: 17,
    printer: { id: "p1", code: "D03", name: "Saturn" },
    technology: "resin",
    status: "printing",
    planned_minutes: 120,
    expected_end_at: null,
    note: "",
    failure_reason: "",
    part_count: 12,
    created_at: "2026-10-29T07:00:00Z",
    started_at: "2026-10-29T08:00:00Z",
    printed_at: null,
    finished_at: null,
    lines: [
      { part: { id: "a", part_number: "DACH", name: "Dach", scale_code: "H0" }, quantity: 4, good: 0, failed: 0 },
      { part: { id: "b", part_number: "SCH", name: "Schornstein", scale_code: "H0" }, quantity: 8, good: 0, failed: 0 },
    ],
    ...overrides,
  };
}

function desk(overrides: Partial<PrinterDeskOut> = {}): PrinterDeskOut {
  return {
    id: "p1",
    code: "D03",
    name: "Saturn",
    model: "",
    technology: "resin",
    build_x_mm: null,
    build_y_mm: null,
    build_z_mm: null,
    notes: "",
    status: "in_service",
    status_note: "",
    status_changed_at: "2026-10-29T07:00:00Z",
    created_at: "2026-10-29T07:00:00Z",
    updated_at: "2026-10-29T07:00:00Z",
    printing: null,
    queue: [],
    ...overrides,
  };
}

describe("deskState", () => {
  it("tells printing, ready and idle printers apart", () => {
    expect(deskState(desk({ printing: job() }))).toBe("printing");
    expect(deskState(desk({ queue: [job({ status: "queued", started_at: null })] }))).toBe("ready");
    expect(deskState(desk())).toBe("idle");
  });

  it("puts the printer's state before its plates", () => {
    expect(deskState(desk({ status: "defective", queue: [job()] }))).toBe("defective");
    expect(deskState(desk({ status: "in_repair" }))).toBe("in_repair");
    expect(deskState(desk({ status: "retired" }))).toBe("retired");
  });
});

describe("plateProgress", () => {
  it("measures the planned time that has passed", () => {
    const progress = plateProgress(job(), new Date("2026-10-29T08:30:00Z"));
    expect(progress).toMatchObject({ fraction: 0.25, elapsedMinutes: 30, remainingMinutes: 90, overdue: false });
    expect(progress?.endsAt.toISOString()).toBe("2026-10-29T10:00:00.000Z");
  });

  it("stops at full and says when it is overdue", () => {
    const progress = plateProgress(job(), new Date("2026-10-29T10:15:00Z"));
    expect(progress).toMatchObject({ fraction: 1, remainingMinutes: -15, overdue: true });
  });

  it("knows nothing without a start or a planned time", () => {
    expect(plateProgress(job({ started_at: null }), new Date())).toBeNull();
    expect(plateProgress(job({ planned_minutes: null }), new Date())).toBeNull();
  });
});

describe("texts", () => {
  it("writes durations like the workshop says them", () => {
    expect(formatMinutes(160)).toBe("2 h 40");
    expect(formatMinutes(240)).toBe("4 h");
    expect(formatMinutes(50)).toBe("50 min");
    expect(formatMinutes(65)).toBe("1 h 05");
  });

  it("names the parts on a plate, the first few", () => {
    expect(plateSummary(job())).toBe("4 × Dach, 8 × Schornstein");
    expect(plateSummary(job(), 1)).toBe("4 × Dach und 1 weitere");
    expect(jobTitle(job())).toBe("Druck 17");
  });

  it("says how long a state has lasted", () => {
    const now = new Date("2026-10-29T12:00:00Z");
    expect(sinceText(new Date("2026-10-29T11:59:30Z"), now)).toBe("seit eben");
    expect(sinceText(new Date("2026-10-29T11:15:00Z"), now)).toBe("seit 45 Minuten");
    expect(sinceText(new Date("2026-10-29T11:00:00Z"), now)).toBe("seit einer Stunde");
    expect(sinceText(new Date("2026-10-28T11:00:00Z"), now)).toBe("seit einem Tag");
    expect(sinceText(new Date("2026-10-26T11:00:00Z"), now)).toBe("seit 3 Tagen");
  });
});

describe("estimateMinutes", () => {
  it("adds every part's share on filament", () => {
    const lines = [
      { plateMinutes: 240, perPlate: 2, quantity: 3 },
      { plateMinutes: 60, perPlate: 20, quantity: 10 },
    ];
    expect(estimateMinutes("fdm", lines)).toBe(390);
  });

  it("takes the slowest part on resin", () => {
    const lines = [
      { plateMinutes: 300, perPlate: 4, quantity: 2 },
      { plateMinutes: 90, perPlate: 12, quantity: 12 },
    ];
    expect(estimateMinutes("resin", lines)).toBe(300);
  });

  it("knows nothing while a part has no plate time", () => {
    expect(estimateMinutes("resin", [{ plateMinutes: null, perPlate: 1, quantity: 1 }])).toBeNull();
    expect(estimateMinutes("fdm", [])).toBeNull();
  });
});
