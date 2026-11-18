import { describe, expect, it } from "vitest";

import type { ScanOut } from "@/lib/api/generated/model";

import {
  contextFor,
  HISTORY_LENGTH,
  initialSession,
  latestAnswer,
  modeOf,
  quantityFor,
  quantityOf,
  SCAN_QUANTITY_MAX,
  scanSession,
  type ScanSession,
} from "./scan-session";

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
    part: null,
    effect: null,
    part_effect: null,
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
    let session = scanned(initialSession("put_away"), "a");
    expect(contextFor(session)).toEqual({});
    session = scanSession(session, {
      type: "answered",
      answer: answer("a", {
        outcome: "selected",
        message: "location_selected",
        location: { code: "R01-F01", name: "Fach 1", kind: "compartment", holds_goods: true, unit_count: 0, part_count: 0 },
      }),
    });
    expect([session.locationCode, session.locationName]).toEqual(["R01-F01", "Fach 1"]);
    expect(contextFor(session)).toEqual({ location_code: "R01-F01" });
    expect(contextFor(scanSession(session, { type: "leave_location" }))).toEqual({});
  });

  it("takes a location on trust while offline, only when putting away", () => {
    const session = scanSession(initialSession("put_away"), { type: "assume_location", code: "R01-F02" });
    expect(contextFor(session)).toEqual({ location_code: "R01-F02" });
    const picking = initialSession("pick", "o-1");
    expect(scanSession(picking, { type: "assume_location", code: "R01-F02" })).toBe(picking);
  });

  it("sends the order while picking and forgets the location on a mode change", () => {
    let session: ScanSession = { ...initialSession("put_away"), locationCode: "R01-F01" };
    session = scanSession(session, { type: "mode", mode: "pick" });
    expect(session.locationCode).toBeNull();
    expect(contextFor(session)).toEqual({});
    session = scanSession(session, { type: "order", orderId: "o-1" });
    expect(contextFor(session)).toEqual({ order_id: "o-1" });
    expect(scanSession(session, { type: "mode", mode: "pick" })).toBe(session);
  });

  it("follows each scan from sending to its answer, queue or failure", () => {
    let session = scanned(scanned(scanned(initialSession("put_away"), "a"), "b"), "c");
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

  it("gives the Anzahl to the next model label and is back at 1 right away", () => {
    let session = scanSession(initialSession("put_away"), { type: "quantity", quantity: 7 });
    expect(quantityFor(session)).toBe(7);
    // A place label leaves the Anzahl for the model label that follows it.
    session = scanned(session, "place", "R01-F01");
    expect([quantityOf(session, "place"), session.quantity]).toEqual([1, 7]);
    session = scanned(session, "a", "2000000000428");
    expect([quantityOf(session, "a"), session.quantity]).toEqual([7, 1]);
    // Scanned before the first answer came (or kept offline): one piece, not seven again.
    session = scanned(session, "b", "2000000000428");
    expect(quantityOf(session, "b")).toBe(1);
    session = scanSession(session, { type: "answered", answer: answer("a", { message: "booked_in" }) });
    expect(session.quantity).toBe(1);
  });

  it("keeps an Anzahl typed for the next label while an earlier one is answered", () => {
    let session = scanned(scanSession(initialSession("put_away"), { type: "quantity", quantity: 7 }), "a", "2000000000428");
    session = scanSession(session, { type: "quantity", quantity: 3 });
    session = scanSession(session, { type: "answered", answer: answer("a", { message: "booked_in" }) });
    expect(session.quantity).toBe(3);
  });

  it("counts an old piece's code like the model's EAN, while booking out too", () => {
    let session = scanSession(scanSession(initialSession("put_away"), { type: "mode", mode: "scrap" }), { type: "quantity", quantity: 4 });
    session = scanned(session, "a", "7KQ2X9F4MZ");
    expect([quantityOf(session, "a"), session.quantity]).toEqual([4, 1]);
    const picking = scanned(scanSession(initialSession("pick", "o-1"), { type: "quantity", quantity: 4 }), "p", "2000000000428");
    expect(quantityOf(picking, "p")).toBe(1);
  });

  it("takes whole numbers from 1 to the most one scan books, and only where they count", () => {
    const count = (quantity: number) => scanSession(initialSession("put_away"), { type: "quantity", quantity }).quantity;
    expect([count(0), count(2.7), count(500), count(Number.NaN)]).toEqual([1, 2, SCAN_QUANTITY_MAX, 1]);
    let picking = scanSession(initialSession("pick", "o-1"), { type: "quantity", quantity: 5 });
    expect(quantityFor(picking)).toBe(1);
    picking = scanSession(scanSession(initialSession("put_away"), { type: "quantity", quantity: 5 }), { type: "mode", mode: "scrap" });
    expect(picking.quantity).toBe(1);
  });

  it("books out with a reason, from the chosen place or from anywhere", () => {
    let session = scanSession(initialSession("put_away"), { type: "mode", mode: "scrap" });
    expect(contextFor(session)).toEqual({ reason: "sold" });
    session = scanSession(session, { type: "reason", reason: "damaged" });
    session = scanSession(session, { type: "assume_location", code: "R01-F02" });
    expect(contextFor(session)).toEqual({ reason: "damaged", location_code: "R01-F02" });
    session = scanSession(session, { type: "leave_location" });
    expect(contextFor(session)).toEqual({ reason: "damaged" });
    // The reason stays when the mode changes and comes back.
    session = scanSession(scanSession(session, { type: "mode", mode: "put_away" }), { type: "mode", mode: "scrap" });
    expect(session.reason).toBe("damaged");
  });

  it("keeps a limited history, newest first", () => {
    let session = initialSession("put_away");
    for (let index = 0; index < HISTORY_LENGTH + 5; index += 1) {
      session = scanned(session, `s${index}`);
    }
    expect(session.entries).toHaveLength(HISTORY_LENGTH);
    expect(session.entries[0]?.scanId).toBe(`s${HISTORY_LENGTH + 4}`);
  });
});

describe("automatic scanning", () => {
  it("starts automatic", () => {
    expect(initialSession()).toMatchObject({ auto: true, mode: "put_away", locationCode: null });
    expect(initialSession("pick", "o1")).toMatchObject({ auto: false, mode: "pick", orderId: "o1" });
  });

  it("looks a label up while no location is open", () => {
    const session = scanned(initialSession(), "a", "2000000000428");
    expect(modeOf(session, "a")).toBe("lookup");
    expect(quantityOf(session, "a")).toBe(1);
  });

  it("opens a scanned location at once and puts the next labels into it", () => {
    let session = scanSession(initialSession(), { type: "quantity", quantity: 3 });
    session = scanned(session, "place", "R01-F01");
    expect(modeOf(session, "place")).toBe("put_away");
    expect(session.locationCode).toBe("R01-F01");
    // Scanned before the location's answer came: it already goes into the location.
    session = scanned(session, "a", "2000000000428");
    expect(modeOf(session, "a")).toBe("put_away");
    expect(quantityOf(session, "a")).toBe(3);
    expect(contextFor({ ...session, mode: modeOf(session, "a") })).toEqual({ location_code: "R01-F01" });
    session = scanSession(session, {
      type: "answered",
      answer: answer("place", { outcome: "selected", location: { code: "R01-F01", name: "Regal 1 · Boden 1" } as ScanOut["location"] }),
    });
    expect(session.locationName).toBe("Regal 1 · Boden 1");
  });

  it("closes a location the server does not know", () => {
    let session = scanned(initialSession(), "place", "R09-F09");
    session = scanSession(session, { type: "answered", answer: answer("place", { outcome: "rejected" as ScanOut["outcome"] }) });
    expect(session.locationCode).toBeNull();
    session = scanned(session, "a", "2000000000428");
    expect(modeOf(session, "a")).toBe("lookup");
  });

  it("leaves automatic when a mode is chosen, and comes back to it", () => {
    let session = scanSession(initialSession(), { type: "mode", mode: "lookup" });
    expect(session).toMatchObject({ auto: false, mode: "lookup" });
    session = scanSession(session, { type: "auto" });
    expect(session).toMatchObject({ auto: true, mode: "put_away" });
  });
});
