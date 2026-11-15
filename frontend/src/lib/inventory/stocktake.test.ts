// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { LocatedUnitOut, LocationOut, UnitOut } from "@/lib/api/generated/model";

import { checkCharacter } from "./codes";
import {
  addFound,
  EMPTY_COUNT,
  expectedPieces,
  foundPiece,
  lookupVerdict,
  recognise,
  removeFound,
  stocktakeBody,
  stocktakeMessage,
  summarise,
  toggleSeen,
  type FoundPiece,
} from "./stocktake";

function code(body: string): string {
  return body + checkCharacter(body);
}

function located(id: string, status: LocatedUnitOut["status"], location: string | null = "R01-F01"): LocatedUnitOut {
  const unitCode = code(`${id.toUpperCase()}0000000`.slice(0, 9));
  return {
    id,
    code: unitCode,
    display_code: `${unitCode.slice(0, 4)} ${unitCode.slice(4, 8)} ${unitCode.slice(8)}`,
    status,
    variant_id: "v1",
    title: "Stellwerk Altenau · H0 · Bausatz",
    sku: "MB-000001-H0-B",
    location_code: location,
    order_number: status === "allocated" ? "MB-2026-0007" : null,
  };
}

const A = located("a1", "in_stock");
const B = located("b1", "allocated");
const C = located("c1", "in_stock");
const BELOW = located("d1", "in_stock", "R01-F01-B1");
const STRAY: FoundPiece = { id: "e1", code: code("E10000000"), display_code: "E100 0000 0x", status: "in_stock", title: null, sku: null, from: "R01-F02" };
const LOST: FoundPiece = { ...STRAY, id: "f1", code: code("F10000000"), status: "scrapped", from: null };

describe("stocktake", () => {
  it("expects only the pieces lying in the place itself", () => {
    expect(expectedPieces([A, B, BELOW, C], "R01-F01")).toEqual([A, B, C]);
  });

  it("ticks, unticks and notes found pieces once", () => {
    let count = toggleSeen(EMPTY_COUNT, "a1");
    count = toggleSeen(count, "b1");
    count = toggleSeen(count, "b1");
    expect([...count.seen]).toEqual(["a1"]);
    expect(toggleSeen(count, "a1", true).seen.has("a1")).toBe(true);
    count = addFound(addFound(count, STRAY), STRAY);
    expect(count.found).toEqual([STRAY]);
    expect(removeFound(count, "e1").found).toEqual([]);
    expect(EMPTY_COUNT.seen.size).toBe(0);
  });

  it("recognises codes: expected here, found already, to look up, or no piece at all", () => {
    const count = addFound(toggleSeen(EMPTY_COUNT, A.id), STRAY);
    expect(recognise(B.code.toLowerCase(), [A, B], count)).toEqual({ kind: "expected", piece: B, already: false });
    expect(recognise(A.display_code, [A, B], count)).toEqual({ kind: "expected", piece: A, already: true });
    expect(recognise(`https://shop.test/u/${STRAY.code}`, [A, B], count)).toEqual({ kind: "found_already", piece: STRAY });
    expect(recognise(C.code, [A, B], count)).toEqual({ kind: "lookup", code: C.code });
    expect(recognise("R01-F02", [A, B], count)).toEqual({ kind: "not_a_unit", reading: "location" });
    expect(recognise("4006381333931", [A, B], count)).toEqual({ kind: "not_a_unit", reading: "variant" });
    expect(recognise("", [A, B], count)).toEqual({ kind: "not_a_unit", reading: null });
  });

  it("tells what a looked-up piece means here", () => {
    const here = { code: "R01-F01" } as LocationOut;
    const there = { code: "R01-F02" } as LocationOut;
    expect(lookupVerdict({ status: "in_stock", location: here }, "R01-F01")).toBe("here");
    expect(lookupVerdict({ status: "allocated", location: there }, "R01-F01")).toBe("found");
    expect(lookupVerdict({ status: "labeled", location: null }, "R01-F01")).toBe("found");
    expect(lookupVerdict({ status: "scrapped", location: null }, "R01-F01")).toBe("found");
    expect(lookupVerdict({ status: "picked", location: null }, "R01-F01")).toBe("order");
    expect(lookupVerdict({ status: "shipped", location: null }, "R01-F01")).toBe("order");
    // A box inside the counted compartment is counted on its own.
    expect(lookupVerdict({ status: "in_stock", location: { code: "R01-F01-B1" } as LocationOut }, "R01-F01")).toBe("below");
    expect(lookupVerdict({ status: "in_stock", location: { code: "R01-F011" } as LocationOut }, "R01-F01")).toBe("found");
    const unit = { id: "e1", code: STRAY.code, display_code: "E100", status: "in_stock", variant: null, location: there } as unknown as UnitOut;
    expect(foundPiece(unit)).toEqual({ id: "e1", code: STRAY.code, display_code: "E100", status: "in_stock", title: null, sku: null, from: "R01-F02" });
  });

  it("sums the count up and sends exactly that", () => {
    const count = addFound(addFound(toggleSeen(EMPTY_COUNT, A.id), STRAY), LOST);
    const summary = summarise([A, B, C], count);
    expect(summary.confirmed).toEqual([A]);
    expect(summary.missing).toEqual([B, C]);
    expect(summary.missingReserved).toEqual([B]);
    expect(summary.found).toEqual([STRAY, LOST]);
    expect(summary.foundScrapped).toEqual([LOST]);
    expect(stocktakeBody(summary)).toEqual({
      present_unit_ids: ["a1"],
      missing_unit_ids: ["b1", "c1"],
      found_unit_ids: ["e1", "f1"],
    });
  });

  it("says what the booking did", () => {
    const location = { code: "R01-F01" } as LocationOut;
    expect(stocktakeMessage({ confirmed: 4, scrapped: 1, found: 2, reserved: 0, location })).toBe(
      "Inventur R01-F01 gebucht: 4 bestätigt, 1 Stück ausgebucht, 2 Stücke hier eingelagert.",
    );
    expect(stocktakeMessage({ confirmed: 3, scrapped: 0, found: 1, reserved: 1, location })).toBe(
      "Inventur R01-F01 gebucht: 3 bestätigt, 1 Stück hier eingelagert. Eins davon ging gleich an wartende Bestellungen.",
    );
    expect(stocktakeMessage({ confirmed: 2, scrapped: 0, found: 0, reserved: 0, location })).toBe(
      "Inventur R01-F01 gebucht: 2 bestätigt.",
    );
  });
});
