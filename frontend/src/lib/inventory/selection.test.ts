// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { LocationOut, UnitMoveOut } from "@/lib/api/generated/model";

import { moveMessage, onlyScrapped, onlyUnbooked, pathLabel, restoreMessage, scrapMessage, unitListHref } from "./selection";

const F02 = { code: "R01-F02" } as LocationOut;

function moved(count: number, there: number, reserved = 0): UnitMoveOut {
  return { moved: count, already_there: there, reserved, location: F02 };
}

describe("selection", () => {
  it("says what a move did, in plain words", () => {
    expect(moveMessage(moved(3, 0), false)).toBe("3 Stücke nach R01-F02 umgelagert.");
    expect(moveMessage(moved(3, 2), false)).toBe("3 Stücke nach R01-F02 umgelagert, 2 lagen schon dort.");
    expect(moveMessage(moved(0, 1), false)).toBe("Nichts gebucht: Das Stück lag schon in R01-F02.");
    expect(moveMessage(moved(0, 4), true)).toBe("Nichts gebucht: Alle lagen schon in R01-F02.");
    expect(moveMessage(moved(2, 0), true)).toBe("2 Stücke in R01-F02 eingelagert. Sie sind jetzt im Shop lieferbar.");
    expect(moveMessage(moved(3, 0, 1), true)).toBe(
      "3 Stücke in R01-F02 eingelagert, 1 davon gleich für eine wartende Bestellung reserviert.",
    );
    expect(moveMessage(moved(3, 0, 2), false)).toBe(
      "3 Stücke nach R01-F02 umgelagert, 2 davon gleich für wartende Bestellungen reserviert.",
    );
  });

  it("says what taking pieces out did", () => {
    expect(scrapMessage({ scrapped: 1, already_scrapped: 1 }, "Beschädigt")).toBe(
      "1 Stück ausgebucht (Beschädigt), 1 war schon ausgebucht.",
    );
    expect(scrapMessage({ scrapped: 0, already_scrapped: 2 }, "Beschädigt")).toBe(
      "Nichts gebucht: Die Stücke waren schon ausgebucht.",
    );
  });

  it("says what booking pieces in again did", () => {
    expect(restoreMessage({ restored: 2, already_there: 0, reserved: 0, location: F02 })).toBe(
      "2 Stücke in R01-F02 wieder eingebucht.",
    );
    expect(restoreMessage({ restored: 1, already_there: 1, reserved: 1, location: F02 })).toBe(
      "1 Stück in R01-F02 wieder eingebucht, 1 lag schon dort, 1 davon gleich für eine wartende Bestellung reserviert.",
    );
    expect(restoreMessage({ restored: 0, already_there: 1, reserved: 0, location: F02 })).toBe(
      "Nichts gebucht: Das Stück lag schon in R01-F02.",
    );
    expect(onlyScrapped(["scrapped"])).toBe(true);
    expect(onlyScrapped(["scrapped", "in_stock"])).toBe(false);
    expect(onlyScrapped([])).toBe(false);
  });

  it("reads paths, tells unbooked selections and links to the lists", () => {
    expect(pathLabel("LAGER.R01.F02")).toBe("LAGER › R01 › F02");
    expect(onlyUnbooked(["labeled", "labeled"])).toBe(true);
    expect(onlyUnbooked(["labeled", "in_stock"])).toBe(false);
    expect(onlyUnbooked([])).toBe(false);
    expect(unitListHref({ filter: "unverbucht" })).toBe("/admin/lager/einheiten?zustand=unverbucht");
    expect(unitListHref({ variantId: "v1" })).toBe("/admin/lager/einheiten?artikel=v1");
  });
});
