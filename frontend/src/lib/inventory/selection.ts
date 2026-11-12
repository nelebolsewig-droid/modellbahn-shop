/*
 * Several pieces ticked in a list and booked together: moved into one place, stored for
 * the first time, or taken out of the stock (backend: UnitService.move_units and
 * scrap_units). Picked, shipped and scrapped pieces cannot be ticked; the backend refuses
 * them as well.
 */

import type { Route } from "next";

import type { UnitMoveOut, UnitScrapOut, UnitStatus } from "@/lib/api/generated/model";

/** Labelled, in the store or reserved there: such a piece can go to a place or out. */
export const SELECTABLE_STATUSES: ReadonlySet<UnitStatus> = new Set(["labeled", "in_stock", "allocated"]);

/** Why a piece cannot be ticked, as the title of its disabled checkbox. */
export const NOT_SELECTABLE_REASONS: Readonly<Partial<Record<UnitStatus, string>>> = {
  picked: "Kommissioniert: liegt beim Packen und gehört zur Bestellung.",
  shipped: "Versendet: hat die Werkstatt verlassen.",
  scrapped: "Ausgebucht: gehört nicht mehr zum Bestand.",
};

/** The list of pieces: of one article (`?artikel=`), in one state (`?zustand=`), or both. */
export function unitListHref({ variantId, filter }: { variantId?: string; filter?: string }): Route {
  const query = new URLSearchParams();
  if (variantId) {
    query.set("artikel", variantId);
  }
  if (filter) {
    query.set("zustand", filter);
  }
  const search = query.toString();
  return (search ? `/admin/lager/einheiten?${search}` : "/admin/lager/einheiten") as Route;
}

export function pieces(count: number): string {
  return count === 1 ? "1 Stück" : `${count} Stücke`;
}

/** `LAGER.R01.F02` as people read it: „LAGER › R01 › F02“. */
export function pathLabel(path: string): string {
  return path.split(".").join(" › ");
}

/** Only labelled pieces, never put away: moving them stores them (Einlagern). */
export function onlyUnbooked(statuses: readonly UnitStatus[]): boolean {
  return statuses.length > 0 && statuses.every((status) => status === "labeled");
}

/** „3 Stücke nach R01-F02 umgelagert, 1 lag schon dort.“ */
export function moveMessage(result: UnitMoveOut, storing: boolean): string {
  const code = result.location.code;
  const there = result.already_there;
  if (result.moved === 0) {
    return `Nichts gebucht: ${there === 1 ? "Das Stück lag" : "Alle lagen"} schon in ${code}.`;
  }
  const done = storing ? `${pieces(result.moved)} in ${code} eingelagert` : `${pieces(result.moved)} nach ${code} umgelagert`;
  const skipped = there > 0 ? `, ${there} ${there === 1 ? "lag" : "lagen"} schon dort` : "";
  const reserved = result.reserved;
  const waiting = reserved > 0 ? `, ${reserved} davon gleich für ${reserved === 1 ? "eine wartende Bestellung" : "wartende Bestellungen"} reserviert` : "";
  // Only pieces that stayed free are sellable; the reserved ones belong to an order now.
  const sellable = storing && reserved === 0 ? (result.moved === 1 ? " Es ist jetzt im Shop lieferbar." : " Sie sind jetzt im Shop lieferbar.") : "";
  return `${done}${skipped}${waiting}.${sellable}`;
}

/** „3 Stücke ausgebucht (Fehlt bei Inventur).“ */
export function scrapMessage(result: UnitScrapOut, reason: string): string {
  const out = result.already_scrapped;
  if (result.scrapped === 0) {
    return "Nichts gebucht: Die Stücke waren schon ausgebucht.";
  }
  const skipped = out > 0 ? `, ${out} ${out === 1 ? "war" : "waren"} schon ausgebucht` : "";
  return `${pieces(result.scrapped)} ausgebucht (${reason})${skipped}.`;
}
