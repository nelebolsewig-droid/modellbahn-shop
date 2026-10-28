/*
 * The scan session as a state machine: which mode, which location or order it works
 * on, and what became of each scan. Pure, so the whole flow is tested without a
 * browser; the scanner page dispatches events and sends what `contextFor` says.
 *
 *   Einlagern:        Platz scannen ─▶ Ware scannen, beliebig oft ─▶ nächster Platz
 *   Kommissionieren:  Bestellung wählen ─▶ jede Ware gegen die Pickliste
 *   Auskunft:         irgendetwas scannen, nichts wird gebucht
 */

import type { ScanMode, ScanOut } from "@/lib/api/generated/model";

export type ScanSource = "camera" | "scanner" | "keyboard";

export type ScanEntry = {
  scanId: string;
  raw: string;
  source: ScanSource;
  mode: ScanMode;
  at: number;
  state: "sending" | "answered" | "waiting" | "failed";
  answer?: ScanOut;
  /** Why it failed, in German (only for `failed`). */
  error?: string;
};

export type ScanSession = {
  mode: ScanMode;
  /** Putting away: the location the next units go into. */
  locationCode: string | null;
  locationName: string | null;
  /** Picking: the order being packed. */
  orderId: string | null;
  /** Newest first. */
  entries: ScanEntry[];
};

export type ScanEvent =
  | { type: "mode"; mode: ScanMode }
  | { type: "order"; orderId: string | null }
  | { type: "leave_location" }
  /** Offline: a location scan cannot be answered, so the device takes it on trust. */
  | { type: "assume_location"; code: string }
  | { type: "scanned"; scanId: string; raw: string; source: ScanSource; at: number }
  | { type: "answered"; answer: ScanOut }
  | { type: "waiting"; scanId: string }
  | { type: "failed"; scanId: string; error: string };

export const HISTORY_LENGTH = 30;

export function initialSession(mode: ScanMode = "put_away", orderId: string | null = null): ScanSession {
  return { mode, locationCode: null, locationName: null, orderId, entries: [] };
}

function updateEntry(session: ScanSession, scanId: string, change: Partial<ScanEntry>): ScanEntry[] {
  return session.entries.map((entry) => (entry.scanId === scanId ? { ...entry, ...change } : entry));
}

export function scanSession(session: ScanSession, event: ScanEvent): ScanSession {
  switch (event.type) {
    case "mode":
      return event.mode === session.mode
        ? session
        : { ...session, mode: event.mode, locationCode: null, locationName: null };
    case "order":
      return { ...session, orderId: event.orderId };
    case "leave_location":
      return { ...session, locationCode: null, locationName: null };
    case "assume_location":
      return session.mode === "put_away" ? { ...session, locationCode: event.code, locationName: null } : session;
    case "scanned": {
      const entry: ScanEntry = {
        scanId: event.scanId,
        raw: event.raw,
        source: event.source,
        mode: session.mode,
        at: event.at,
        state: "sending",
      };
      return { ...session, entries: [entry, ...session.entries].slice(0, HISTORY_LENGTH) };
    }
    case "answered": {
      const { answer } = event;
      const entries = updateEntry(session, answer.scan_id, { state: "answered", answer });
      // A location scanned while putting away becomes the place for what follows.
      if (answer.outcome === "selected" && answer.location !== null) {
        return { ...session, entries, locationCode: answer.location.code, locationName: answer.location.name };
      }
      return { ...session, entries };
    }
    case "waiting":
      return { ...session, entries: updateEntry(session, event.scanId, { state: "waiting" }) };
    case "failed":
      return { ...session, entries: updateEntry(session, event.scanId, { state: "failed", error: event.error }) };
  }
}

/** What the server needs to know besides the code: the location, or the order. */
export function contextFor(session: ScanSession): Partial<Record<"location_code" | "order_id", string>> {
  if (session.mode === "put_away" && session.locationCode !== null) {
    return { location_code: session.locationCode };
  }
  if (session.mode === "pick" && session.orderId !== null) {
    return { order_id: session.orderId };
  }
  return {};
}

/** The newest answered entry, to show large; null before the first answer. */
export function latestAnswer(session: ScanSession): ScanEntry | null {
  return session.entries.find((entry) => entry.state !== "sending") ?? null;
}
