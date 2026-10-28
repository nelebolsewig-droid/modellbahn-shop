import { describe, expect, it } from "vitest";

import type { ScanOut } from "@/lib/api/generated/model";

import { contextFor, HISTORY_LENGTH, initialSession, latestAnswer, scanSession, type ScanSession } from "./scan-session";

function answer(scanId: string, change: Partial<ScanOut>): ScanOut {
  return {
    scan_id: scanId,
    mode: "put_away",
    outcome: "applied",
    message: "put_away",
    resolved: null,
    unit: null,
    location: null,
    variant: null,
    effect: null,
    progress: null,
    next_expected: null,
    undoable: true,
    undone: false,
    ...change,
  };
}

function scanned(session: ScanSession, scanId: string, raw = "R01-F01"): ScanSession {
  return scanSession(session, { type: "scanned", scanId, raw, source: "camera", at: 0 });
}

describe("scan session", () => {
  it("chooses the location while putting away and sends it with the next scans", () => {
    let session = scanned(initialSession(), "a");
    expect(contextFor(session)).toEqual({});
    session = scanSession(session, {
      type: "answered",
      answer: answer("a", {
        outcome: "selected",
        message: "location_selected",
        location: { code: "R01-F01", name: "Fach 1", kind: "compartment", holds_goods: true, unit_count: 0 },
      }),
    });
    expect([session.locationCode, session.locationName]).toEqual(["R01-F01", "Fach 1"]);
    expect(contextFor(session)).toEqual({ location_code: "R01-F01" });
    expect(contextFor(scanSession(session, { type: "leave_location" }))).toEqual({});
  });

  it("takes a location on trust while offline, only when putting away", () => {
    const session = scanSession(initialSession(), { type: "assume_location", code: "R01-F02" });
    expect(contextFor(session)).toEqual({ location_code: "R01-F02" });
    const picking = initialSession("pick", "o-1");
    expect(scanSession(picking, { type: "assume_location", code: "R01-F02" })).toBe(picking);
  });

  it("sends the order while picking and forgets the location on a mode change", () => {
    let session = { ...initialSession(), locationCode: "R01-F01" };
    session = scanSession(session, { type: "mode", mode: "pick" });
    expect(session.locationCode).toBeNull();
    expect(contextFor(session)).toEqual({});
    session = scanSession(session, { type: "order", orderId: "o-1" });
    expect(contextFor(session)).toEqual({ order_id: "o-1" });
    expect(scanSession(session, { type: "mode", mode: "pick" })).toBe(session);
  });

  it("follows each scan from sending to its answer, queue or failure", () => {
    let session = scanned(scanned(scanned(initialSession(), "a"), "b"), "c");
    expect(latestAnswer(session)).toBeNull();
    session = scanSession(session, { type: "answered", answer: answer("a", {}) });
    session = scanSession(session, { type: "waiting", scanId: "b" });
    session = scanSession(session, { type: "failed", scanId: "c", error: "kaputt" });
    expect(session.entries.map((entry) => [entry.scanId, entry.state])).toEqual([
      ["c", "failed"],
      ["b", "waiting"],
      ["a", "answered"],
    ]);
    expect(latestAnswer(session)?.scanId).toBe("c");
  });

  it("keeps a limited history, newest first", () => {
    let session = initialSession();
    for (let index = 0; index < HISTORY_LENGTH + 5; index += 1) {
      session = scanned(session, `s${index}`);
    }
    expect(session.entries).toHaveLength(HISTORY_LENGTH);
    expect(session.entries[0].scanId).toBe(`s${HISTORY_LENGTH + 4}`);
  });
});
