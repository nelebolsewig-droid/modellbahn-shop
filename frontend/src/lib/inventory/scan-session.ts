/*
 * The scan session as a state machine: which mode, which location or order it works
 * on, how many pieces the next model label stands for, and what became of each scan.
 * Pure, so the whole flow is tested without a browser; the scanner page dispatches
 * events and sends what `contextFor` and `quantityOf` say.
 *
 *   Einlagern:        Platz scannen ─▶ Anzahl, Modell scannen, beliebig oft ─▶ nächster Platz
 *   Kommissionieren:  Bestellung wählen ─▶ jede Ware gegen die Pickliste
 *   Ausbuchen:        Grund, Platz (wenn er zählt), Anzahl ─▶ Modell scannen
 *   Auskunft:         irgendetwas scannen, nichts wird gebucht
 *
 * A model label takes the Anzahl along the moment it is scanned, and the Anzahl goes
 * back to 1 right then: the next label, scanned before the answer came or kept offline,
 * counts one piece unless someone says otherwise. A place or part label leaves it be.
 */

import type { ScanMode, ScanOut, ScrapReason } from "@/lib/api/generated/model";

import { interpretations } from "./codes";

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
  /**
   * Automatic: no mode to choose. A location opens it for putting away, a label then goes
   * into it; a label without a location shows what is known about it (ADR 0033).
   * `mode` is then the putting away the location belongs to.
   */
  auto: boolean;
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
  | { type: "auto" }
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

/** Starts automatic, unless a mode is asked for (picking an order from the order desk). */
export function initialSession(mode: ScanMode | "auto" = "auto", orderId: string | null = null): ScanSession {
  return {
    auto: mode === "auto",
    mode: mode === "auto" ? "put_away" : mode,
    locationCode: null,
    locationName: null,
    orderId,
    quantity: 1,
    reason: "sold",
    entries: [],
  };
}

/**
 * The mode an automatic scan goes out in: a location is put-away's place; a label goes
 * into the open place, or, without one, is looked up.
 */
export function autoModeFor(session: Pick<ScanSession, "locationCode">, raw: string): ScanMode {
  const kind = interpretations(raw)[0]?.kind;
  if (kind === "location" || session.locationCode !== null) {
    return "put_away";
  }
  return "lookup";
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
    case "auto":
      return session.auto
        ? session
        : { ...session, auto: true, mode: "put_away", locationCode: null, locationName: null, quantity: 1 };
    case "mode":
      return event.mode === session.mode && !session.auto
        ? session
        : { ...session, auto: false, mode: event.mode, locationCode: null, locationName: null, quantity: 1 };
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
      const mode = session.auto ? autoModeFor(session, event.raw) : session.mode;
      const counts = COUNTING_MODES.has(mode) && namesModel(event.raw);
      const entry: ScanEntry = {
        scanId: event.scanId,
        raw: event.raw,
        source: event.source,
        mode,
        quantity: counts ? session.quantity : 1,
        at: event.at,
        state: "sending",
      };
      // Automatic: a location opens at once, so a label scanned before the answer
      // comes already goes into it. The answer names it, or closes it again.
      const reading = interpretations(event.raw)[0];
      const opens = session.auto && reading?.kind === "location";
      return {
        ...session,
        ...(opens && { locationCode: reading.code, locationName: null }),
        quantity: counts ? 1 : session.quantity,
        entries: [entry, ...session.entries].slice(0, HISTORY_LENGTH),
      };
    }
    case "answered": {
      const { answer } = event;
      const entries = updateEntry(session, answer.scan_id, { state: "answered", answer });
      // A location scanned while putting away or booking out becomes the place for what follows.
      if (answer.outcome === "selected" && answer.location !== null) {
        return { ...session, entries, locationCode: answer.location.code, locationName: answer.location.name };
      }
      // An automatic location the server does not know closes again.
      const scannedEntry = session.entries.find((candidate) => candidate.scanId === answer.scan_id);
      if (
        session.auto &&
        scannedEntry !== undefined &&
        interpretations(scannedEntry.raw)[0]?.kind === "location" &&
        session.locationCode === interpretations(scannedEntry.raw)[0]?.code &&
        session.locationName === null
      ) {
        return { ...session, entries, locationCode: null };
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

/** How many pieces the next model label books: the Anzahl when it counts, else one. */
export function quantityFor(session: ScanSession): number {
  return COUNTING_MODES.has(session.mode) ? session.quantity : 1;
}

/** Whether a scanned code reads first of all as a model's label (EAN or an old piece's code). */
function namesModel(raw: string): boolean {
  const kind = interpretations(raw)[0]?.kind;
  return kind === "variant" || kind === "unit";
}

/** The mode a scan was taken in (automatic scans choose theirs when scanned). */
export function modeOf(session: ScanSession, scanId: string): ScanMode {
  return session.entries.find((entry) => entry.scanId === scanId)?.mode ?? session.mode;
}

/** The Anzahl a scan took along when it was scanned (1 for anything but a model label). */
export function quantityOf(session: ScanSession, scanId: string): number {
  return session.entries.find((entry) => entry.scanId === scanId)?.quantity ?? 1;
}

/** The newest answered entry, to show large; null before the first answer. */
export function latestAnswer(session: ScanSession): ScanEntry | null {
  return session.entries.find((entry) => entry.state !== "sending") ?? null;
}
