/*
 * Counting one place (Inventur), kept in the browser until it is booked. Every piece the
 * journal has in the place is ticked once it is seen, by hand or by scanning its label;
 * pieces scanned there that the journal has elsewhere, unbooked or scrapped are noted as
 * found. Booking it all is one request (backend: UnitService.take_stock): missing pieces
 * leave the stock as „Fehlt bei Inventur“, found ones are put away in the place.
 */

import type { LocatedUnitOut, StocktakeIn, StocktakeOut, UnitOut, UnitStatus } from "@/lib/api/generated/model";

import { interpretations } from "./codes";
import { pieces } from "./selection";

/** A piece scanned in the place that the journal has somewhere else. */
export type FoundPiece = {
  id: string;
  code: string;
  display_code: string;
  status: UnitStatus;
  title: string | null;
  sku: string | null;
  /** The place the journal has it in; null when unbooked or scrapped. */
  from: string | null;
};

export type Count = {
  /** Ids of the expected pieces seen in the place. */
  seen: ReadonlySet<string>;
  found: readonly FoundPiece[];
};

export const EMPTY_COUNT: Count = { seen: new Set(), found: [] };

/** The pieces the journal has in the place itself (not in places below it). */
export function expectedPieces(units: readonly LocatedUnitOut[], here: string): LocatedUnitOut[] {
  return units.filter((unit) => unit.location_code === here && (unit.status === "in_stock" || unit.status === "allocated"));
}

export function toggleSeen(count: Count, id: string, on?: boolean): Count {
  const seen = new Set(count.seen);
  if (on ?? !seen.has(id)) {
    seen.add(id);
  } else {
    seen.delete(id);
  }
  return { ...count, seen };
}

export function addFound(count: Count, piece: FoundPiece): Count {
  return count.found.some((other) => other.id === piece.id) ? count : { ...count, found: [...count.found, piece] };
}

export function removeFound(count: Count, id: string): Count {
  return { ...count, found: count.found.filter((piece) => piece.id !== id) };
}

/** What a scanned or typed code means for the count, before asking the server. */
export type Recognised =
  | { kind: "expected"; piece: LocatedUnitOut; already: boolean }
  | { kind: "found_already"; piece: FoundPiece }
  /** A piece's code that the place does not expect: the server knows where it is. */
  | { kind: "lookup"; code: string }
  /** No piece's code: a place, a part, an article's EAN, or nothing readable. */
  | { kind: "not_a_unit"; reading: "variant" | "location" | "part" | null };

export function recognise(raw: string, expected: readonly LocatedUnitOut[], count: Count): Recognised {
  const readings = interpretations(raw);
  const unit = readings.find((reading) => reading.kind === "unit");
  if (unit === undefined) {
    const first = readings[0];
    return { kind: "not_a_unit", reading: first ? (first.kind as "variant" | "location" | "part") : null };
  }
  const piece = expected.find((candidate) => candidate.code === unit.code);
  if (piece !== undefined) {
    return { kind: "expected", piece, already: count.seen.has(piece.id) };
  }
  const found = count.found.find((candidate) => candidate.code === unit.code);
  if (found !== undefined) {
    return { kind: "found_already", piece: found };
  }
  return { kind: "lookup", code: unit.code };
}

/**
 * How a piece looked up by its code counts here: lying here after all (it came during
 * the count), found here, not to be stored because it belongs to an order's parcel, or
 * booked in a place inside this one (a box in the compartment), which is counted on its own.
 */
export function lookupVerdict(unit: Pick<UnitOut, "status" | "location">, here: string): "here" | "found" | "order" | "below" {
  if (unit.status === "picked" || unit.status === "shipped") {
    return "order";
  }
  const code = unit.location?.code;
  if (code === here) {
    return "here";
  }
  return code?.startsWith(`${here}-`) ? "below" : "found";
}

export function foundPiece(unit: UnitOut): FoundPiece {
  return {
    id: unit.id,
    code: unit.code,
    display_code: unit.display_code,
    status: unit.status,
    title: unit.variant?.title ?? null,
    sku: unit.variant?.sku ?? null,
    from: unit.location?.code ?? null,
  };
}

export type Summary = {
  confirmed: LocatedUnitOut[];
  missing: LocatedUnitOut[];
  /** Missing pieces reserved for an order: it gets another piece or waits. */
  missingReserved: LocatedUnitOut[];
  found: FoundPiece[];
  /** Found pieces that were scrapped: they are booked in again. */
  foundScrapped: FoundPiece[];
};

export function summarise(expected: readonly LocatedUnitOut[], count: Count): Summary {
  const confirmed = expected.filter((piece) => count.seen.has(piece.id));
  const missing = expected.filter((piece) => !count.seen.has(piece.id));
  return {
    confirmed,
    missing,
    missingReserved: missing.filter((piece) => piece.status === "allocated"),
    found: [...count.found],
    foundScrapped: count.found.filter((piece) => piece.status === "scrapped"),
  };
}

export function stocktakeBody(summary: Summary): StocktakeIn {
  return {
    present_unit_ids: summary.confirmed.map((piece) => piece.id),
    missing_unit_ids: summary.missing.map((piece) => piece.id),
    found_unit_ids: summary.found.map((piece) => piece.id),
  };
}

/** „Inventur R01-F01 gebucht: 4 bestätigt, 1 Stück ausgebucht, 2 Stücke hier eingelagert.“ */
export function stocktakeMessage(result: StocktakeOut): string {
  const parts = [`${result.confirmed} bestätigt`];
  if (result.scrapped > 0) {
    parts.push(`${pieces(result.scrapped)} ausgebucht`);
  }
  if (result.found > 0) {
    parts.push(`${pieces(result.found)} hier eingelagert`);
  }
  const reserved = result.reserved;
  const waiting = reserved > 0 ? ` ${reserved === 1 ? "Eins davon ging" : `${reserved} davon gingen`} gleich an wartende Bestellungen.` : "";
  return `Inventur ${result.location.code} gebucht: ${parts.join(", ")}.${waiting}`;
}
