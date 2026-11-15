/*
 * The scan session as a state machine: which mode, which location or order it works
 * on, how many pieces the next model label stands for, and what became of each scan.
 * Pure, so the whole flow is tested without a browser; the scanner page dispatches
 * events and sends what `contextFor` and `quantityFor` say.
 *
 *   Einlagern:        Platz scannen ─▶ Anzahl, Modell scannen, beliebig oft ─▶ nächster Platz
 *   Kommissionieren:  Bestellung wählen ─▶ jede Ware gegen die Pickliste
 *   Ausbuchen:        Grund, Platz (wenn er zählt), Anzahl ─▶ Modell scannen
 *   Auskunft:         irgendetwas scannen, nichts wird gebucht
 *
 * The Anzahl goes back to 1 once a scan with it was booked, so the next label counts
 * one piece unless someone says otherwise.
 */

import type { ScanMode, ScanOut, ScrapReason } from "@/lib/api/generated/model";

export type ScanSource = "camera" | "scanner" | "keyboard";

export type ScanEntry = {
  scanId: string;
  raw: string;
  source: ScanSource;
  mode: ScanMode;
  /** The Anzahl the scan was sent with. */
  quantity: number;
  at: number;
  state: "sending" | "answered" | "waiting" | "failed";
  answer?: ScanOut;
  /** Why it failed, in German (only for `failed`). */
  error?: string;
};

export type ScanSession = {
  mode: ScanMode;
  /** Putting away: the location the next pieces go into; booking out: the one they leave. */
  locationCode: string | null;
  locationName: string | null;
  /** Picking: the order being packed. */
  orderId: string | null;
  /** Putting away and booking out: how many pieces the next model label stands for. */
  quantity: number;
  /** Booking out: why the pieces leave the stock. */
  reason: ScrapReason;
  /** Newest first. */
  entries: ScanEntry[];
};

/** The modes in which a model label stands for an Anzahl of pieces. */
export const COUNTING_MODES: ReadonlySet<ScanMode> = new Set(["put_away", "scrap"]);

/** As many pieces as one scan books (the backend's SCAN_QUANTITY_MAX). */
export const SCAN_QUANTITY_MAX = 200;

export type ScanEvent =
  | { type: "mode"; mode: ScanMode }
  | { type: "order"; orderId: string | null }
  | { type: "leave_location" }
  /** Offline: a location scan cannot be answered, so the device takes it on trust. */
  | { type: "assume_location"; code: string }
  | { type: "quantity"; quantity: number }
  | { type: "reason"; reason: ScrapReason }
  | { type: "scanned"; scanId: string; raw: string; source: ScanSource; at: number }
  | { type: "answered"; answer: ScanOut }
  | { type: "waiting"; scanId: string }
  | { type: "failed"; scanId: string; error: string };

export const HISTORY_LENGTH = 30;

export function initialSession(mode: ScanMode = "put_away", orderId: string | null = null): ScanSession {
  return { mode, locationCode: null, locationName: null, orderId, quantity: 1, reason: "sold", entries: [] };
}

/** A whole number from 1 to the most one scan books. */
function clampQuantity(quantity: number): number {
  return Number.isFinite(quantity) ? Math.min(SCAN_QUANTITY_MAX, Math.max(1, Math.trunc(quantity))) : 1;
}

function updateEntry(session: ScanSession, scanId: string, change: Partial<ScanEntry>): ScanEntry[] {
  return session.entries.map((entry) => (entry.scanId === scanId ? { ...entry, ...change } : entry));
}

export function scanSession(session: ScanSession, event: ScanEvent): ScanSession {
  switch (event.type) {
    case "mode":
      return event.mode === session.mode
        ? session
        : { ...session, mode: event.mode, locationCode: null, locationName: null, quantity: 1 };
    case "order":
      return { ...session, orderId: event.orderId };
    case "leave_location":
      return { ...session, locationCode: null, locationName: null };
    case "assume_location":
      return COUNTING_MODES.has(session.mode) ? { ...session, locationCode: event.code, locationName: null } : session;
    case "quantity":
      return { ...session, quantity: clampQuantity(event.quantity) };
    case "reason":
      return { ...session, reason: event.reason };
    case "scanned": {
      const entry: ScanEntry = {
        scanId: event.scanId,
        raw: event.raw,
        source: event.source,
        mode: session.mode,
        quantity: quantityFor(session),
        at: event.at,
        state: "sending",
      };
      return { ...session, entries: [entry, ...session.entries].slice(0, HISTORY_LENGTH) };
    }
    case "answered": {
      const { answer } = event;
      const entry = session.entries.find((item) => item.scanId === answer.scan_id);
      const entries = updateEntry(session, answer.scan_id, { state: "answered", answer });
      // A location scanned while putting away or booking out becomes the place for what follows.
      if (answer.outcome === "selected" && answer.location !== null) {
        return { ...session, entries, locationCode: answer.location.code, locationName: answer.location.name };
      }
      // Booked with the Anzahl that is still set: the next label counts one piece again.
      const booked = answer.outcome === "applied" && !answer.undone && answer.mode === session.mode;
      if (booked && entry !== undefined && entry.quantity === session.quantity) {
        return { ...session, entries, quantity: 1 };
      }
      return { ...session, entries };
    }
    case "waiting":
      return { ...session, entries: updateEntry(session, event.scanId, { state: "waiting" }) };
    case "failed":
      return { ...session, entries: updateEntry(session, event.scanId, { state: "failed", error: event.error }) };
  }
}

/** What the server needs to know besides the code: the location, the order, the reason. */
export function contextFor(session: ScanSession): Partial<Record<"location_code" | "order_id" | "reason", string>> {
  if (session.mode === "put_away" && session.locationCode !== null) {
    return { location_code: session.locationCode };
  }
  if (session.mode === "pick" && session.orderId !== null) {
    return { order_id: session.orderId };
  }
  if (session.mode === "scrap") {
    return session.locationCode === null
      ? { reason: session.reason }
      : { reason: session.reason, location_code: session.locationCode };
  }
  return {};
}

/** How many pieces the next scan books: the Anzahl when it counts, else one. */
export function quantityFor(session: ScanSession): number {
  return COUNTING_MODES.has(session.mode) ? session.quantity : 1;
}

/** The newest answered entry, to show large; null before the first answer. */
export function latestAnswer(session: ScanSession): ScanEntry | null {
  return session.entries.find((entry) => entry.state !== "sending") ?? null;
}
