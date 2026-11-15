/*
 * Stock by number (ADR 0028): how the Stellwerk words what lies where, and what a count
 * books. Pure, so it is tested without a browser.
 */

import type { CountLineIn, PlaceStockOut, PlaceTotalOut } from "@/lib/api/generated/model";

/** Places shown in one line before "+ N weitere". */
const PLACES_SHOWN = 2;

/** `7 · Regal 2, Boden 3; 2 · Regal 1, Boden 1 + 1 weiterer Platz` */
export function placesLine(places: readonly PlaceTotalOut[]): string {
  const shown = places.slice(0, PLACES_SHOWN).map((place) => `${place.quantity} · ${place.place}`);
  const rest = places.length - PLACES_SHOWN;
  const more = rest > 0 ? ` + ${rest === 1 ? "1 weiterer Platz" : `${rest} weitere Plätze`}` : "";
  return `${shown.join("; ")}${more}`;
}

/** Pieces lying in a place: free and reserved together, as the count expects them. */
export function lying(line: Pick<PlaceStockOut, "free" | "reserved">): number {
  return line.free + line.reserved;
}

/** One line of a count: what the Stellwerk shows, what was counted. */
export type CountEntry = { variantId: string; locationCode: string; expected: number; counted: number };

/** The lines a count books: only those where the number counted differs. */
export function countLines(entries: readonly CountEntry[]): CountLineIn[] {
  return entries
    .filter((entry) => entry.counted !== entry.expected)
    .map((entry) => ({
      variant_id: entry.variantId,
      location_code: entry.locationCode,
      expected: entry.expected,
      counted: entry.counted,
    }));
}

/** `2 fehlen, 3 dazu`: what a count booked, in a few words. */
export function countMessage(result: { missing: number; added: number; reserved: number }): string {
  if (result.missing === 0 && result.added === 0) {
    return "Alles stimmt, nichts gebucht.";
  }
  const parts = [
    result.missing > 0 ? `${result.missing} ${result.missing === 1 ? "fehlendes Stück" : "fehlende Stücke"} ausgebucht` : "",
    result.added > 0 ? `${result.added} ${result.added === 1 ? "Stück" : "Stücke"} dazu eingebucht` : "",
  ].filter(Boolean);
  const waiting = result.reserved > 0 ? `, ${result.reserved} davon gleich für wartende Bestellungen reserviert` : "";
  return `${parts.join(", ")}${waiting}.`;
}
