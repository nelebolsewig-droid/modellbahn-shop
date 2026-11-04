import { describe, expect, it } from "vitest";

import type { PartHistoryEntryOut, ReceiptOut } from "@/lib/api/generated/model";

import { binLevel, coverage, partMovementText, receivingSlips } from "./parts";

function receipt(id: string, job: { id: string; number: number; at: string } | null, open: number): ReceiptOut {
  return {
    id,
    part: null,
    print_job: job ? { job_id: job.id, number: job.number, printer_code: "D04", finished_at: job.at } : null,
    quantity: open,
    stored: 0,
    written_off: 0,
    open,
    created_at: "2026-10-30T08:00:00Z",
  };
}

function entry(overrides: Partial<PartHistoryEntryOut>): PartHistoryEntryOut {
  return {
    id: 1,
    reason: "receive",
    quantity: 7,
    from_location_code: null,
    to_location_code: null,
    print_job_number: null,
    unit_code: null,
    note: "",
    staff_name: null,
    scan_id: null,
    reverses_id: null,
    occurred_at: "2026-10-30T08:00:00Z",
    ...overrides,
  };
}

describe("receivingSlips", () => {
  it("puts the parts of one plate on one delivery note, the oldest plate first", () => {
    const late = { id: "j18", number: 18, at: "2026-10-30T09:00:00Z" };
    const early = { id: "j17", number: 17, at: "2026-10-30T07:00:00Z" };
    const slips = receivingSlips([receipt("a", late, 4), receipt("b", early, 7), receipt("c", early, 3)]);
    expect(slips.map((slip) => [slip.number, slip.receipts.length, slip.open])).toEqual([
      [17, 2, 10],
      [18, 1, 4],
    ]);
  });
});

describe("partMovementText", () => {
  it("says where the parts went, in German", () => {
    expect(partMovementText(entry({ print_job_number: 17, to_location_code: "R01-F01-B02" }))).toBe(
      "7 Teile aus Druck 17 in R01-F01-B02",
    );
    expect(
      partMovementText(
        entry({ reason: "assemble", quantity: 1, from_location_code: "R01-F01-B02", unit_code: "7KQ2X9F4MZ" }),
      ),
    ).toBe("1 Teil aus R01-F01-B02 in 7KQ2 X9F4 MZ");
    expect(partMovementText(entry({ reason: "count", quantity: 2, from_location_code: "B02" }))).toBe(
      "2 Teile weniger gezählt in B02",
    );
    expect(partMovementText(entry({ reason: "count", quantity: 3, to_location_code: "B02" }))).toBe(
      "3 Teile mehr gezählt in B02",
    );
    expect(partMovementText(entry({ reason: "write_off", print_job_number: 17 }))).toBe(
      "7 Teile aus Druck 17 ausgebucht",
    );
    expect(partMovementText(entry({ reason: "undo", from_location_code: "B02" }))).toBe(
      "7 Teile aus B02 zurück in den Wareneingang",
    );
  });
});

describe("coverage and bins", () => {
  it("measures how far the stock covers an assembly", () => {
    expect(coverage({ needed: 4, available: 1 })).toBe(0.25);
    expect(coverage({ needed: 4, available: 9 })).toBe(1);
    expect(coverage({ needed: 0, available: 0 })).toBe(1);
  });

  it("fills a bin relative to the fullest one, never invisibly little", () => {
    expect(binLevel(0, 10)).toBe(0);
    expect(binLevel(1, 100)).toBe(0.12);
    expect(binLevel(5, 10)).toBe(0.5);
  });
});
