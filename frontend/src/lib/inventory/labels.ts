import type { StatusTone } from "@/components/ui/status-badge";
import type {
  LocationKind,
  MovementReason,
  PartMovementReason,
  PieceState,
  ScanMode,
  ScrapReason,
  ScanOut,
  ScanOutcome,
  ScanOutMessage,
  ScanStockEffectOut,
  UnitStatus,
} from "@/lib/api/generated/model";

/** German names of the workshop's states, places and movements. */

export const UNIT_STATUS_LABELS: Readonly<Record<UnitStatus, string>> = {
  labeled: "Etikettiert",
  in_stock: "Im Lager",
  allocated: "Reserviert",
  picked: "Kommissioniert",
  shipped: "Versendet",
  scrapped: "Ausgebucht",
};

/** Why a piece was taken out of the stock by hand (Ausbuchen). */
export const SCRAP_REASON_LABELS: Readonly<Record<ScrapReason, string>> = {
  sold: "Verkauft (Messe, Laden, privat)",
  damaged: "Beschädigt",
  missing: "Fehlt bei Inventur",
  mistake: "Versehen",
};

export const UNIT_STATUS_TONES: Readonly<Record<UnitStatus, StatusTone>> = {
  labeled: "warning",
  in_stock: "success",
  allocated: "accent",
  picked: "accent",
  shipped: "neutral",
  scrapped: "danger",
};

export const PIECE_STATE_LABELS: Readonly<Record<PieceState, string>> = {
  backordered: "Wartet auf Fertigung",
  reserved: "Reserviert",
  picked: "Kommissioniert",
  shipped: "Versendet",
  released: "Freigegeben",
};

export const PIECE_STATE_TONES: Readonly<Record<PieceState, StatusTone>> = {
  backordered: "warning",
  reserved: "accent",
  picked: "success",
  shipped: "neutral",
  released: "neutral",
};

export const LOCATION_KIND_LABELS: Readonly<Record<LocationKind, string>> = {
  site: "Lager",
  shelf: "Regal",
  compartment: "Fach",
  box: "Box",
  staging: "Ablage",
};

/** Which kinds may be placed below which (mirrors the backend's rule). */
export const CHILD_KINDS: Readonly<Record<LocationKind | "root", readonly LocationKind[]>> = {
  root: ["site"],
  site: ["shelf", "staging"],
  shelf: ["compartment", "box"],
  compartment: ["box"],
  box: [],
  staging: [],
};

export const MOVEMENT_LABELS: Readonly<Record<MovementReason, string>> = {
  label: "Etikett gedruckt",
  put_away: "Eingelagert",
  move: "Umgelagert",
  allocate: "Für Bestellung reserviert",
  release: "Freigegeben",
  pick: "Kommissioniert",
  ship: "Versendet",
  scrap: "Ausgebucht",
  undo: "Rückgängig gemacht",
  restore: "Wieder eingebucht",
  correct: "Ausführung geändert",
};

/** What happened to printed parts, as the parts journal says it. */
export const PART_MOVEMENT_LABELS: Readonly<Record<PartMovementReason, string>> = {
  receive: "Eingelagert",
  assemble: "Montiert",
  count: "Gezählt",
  write_off: "Ausgebucht",
  undo: "Rückgängig gemacht",
};

export const SCAN_MODE_LABELS: Readonly<Record<ScanMode, string>> = {
  put_away: "Einlagern",
  pick: "Kommissionieren",
  scrap: "Ausbuchen",
  lookup: "Auskunft",
};

export const OUTCOME_LABELS: Readonly<Record<ScanOutcome, string>> = {
  applied: "Gebucht",
  selected: "Gewählt",
  info: "Auskunft",
  rejected: "Abgelehnt",
  unknown: "Unbekannt",
};

export const OUTCOME_TONES: Readonly<Record<ScanOutcome, StatusTone>> = {
  applied: "success",
  selected: "accent",
  info: "neutral",
  rejected: "warning",
  unknown: "danger",
};

const MESSAGES: Readonly<Record<ScanOutMessage, string>> = {
  unknown_code: "Diesen Code kennt das Lager nicht.",
  not_found: "Dazu gibt es nichts im Lager.",
  unit: "Stück",
  location: "Platz",
  variant: "Modell",
  location_selected: "Platz gewählt. Jetzt die Ware scannen.",
  location_required: "Erst den Platz scannen, dann die Ware.",
  location_unknown: "Den gewählten Platz gibt es nicht mehr. Bitte neu scannen.",
  holds_no_goods: "Hier kommt keine Ware hinein: nur Fächer, Boxen und Ablagen.",
  already_there: "Liegt schon hier.",
  unit_gone: "Dieses Stück ist versendet oder ausgebucht.",
  unit_picked: "Dieses Stück ist für eine Bestellung kommissioniert.",
  put_away: "Eingelagert.",
  move: "Umgelagert.",
  no_unit_to_store: "Kein unverbuchtes Stück dieses Modells. Bitte das Etikett des Stücks scannen.",
  scan_unit_label: "Bitte das Etikett des Modells scannen.",
  order_unknown: "Diese Bestellung gibt es nicht. Bitte neu wählen.",
  order_not_pickable: "Diese Bestellung ist nicht bezahlt oder noch nicht zugeteilt.",
  picked: "Kommissioniert.",
  already_picked: "Schon kommissioniert.",
  reserved_for_other_order: "Falsches Stück: Es ist für eine andere Bestellung reserviert.",
  variant_complete: "Von diesem Modell ist schon alles kommissioniert.",
  not_in_order: "Falsches Modell: Es gehört nicht zu dieser Bestellung.",
  unit_not_stored: "Dieses Stück ist noch nicht eingelagert.",
  variant_not_in_stock: "Kein Stück dieses Modells im Lager.",
  part: "Teil",
  parts_stored: "Teile eingelagert.",
  no_parts_to_store: "Von diesem Teil wartet nichts im Wareneingang.",
  booked_in: "Eingebucht.",
  booked_out: "Ausgebucht.",
  not_enough_free: "Nicht genug freie Stücke. Nichts ausgebucht.",
  book_in_not_allowed:
    "Neue Stücke einbuchen dürfen nur Inhaber und Mitarbeiter. Es liegen nicht genug unverbuchte Stücke vor; nichts gebucht.",
};

/** The reasons as one word, for the answer to a scan. */
const SCRAP_REASON_SHORT: Readonly<Record<ScrapReason, string>> = {
  sold: "Verkauft",
  damaged: "Beschädigt",
  missing: "Fehlt",
  mistake: "Versehen",
};

/** `+7 · jetzt 9 hier`: what a model's label booked in, in a few words. */
function bookedIn(effect: ScanStockEffectOut): string {
  const here = effect.in_location === null ? "" : ` · jetzt ${effect.in_location} hier`;
  const reserved = effect.reserved > 0 ? ` · ${effect.reserved} gleich reserviert` : "";
  return `+${effect.quantity}${here}${reserved}`;
}

/** `−3 · Verkauft · noch 2 hier` (or `noch 5 frei` without a place). */
function bookedOut(answer: ScanOut, effect: ScanStockEffectOut): string {
  const reason = effect.reason ? ` · ${SCRAP_REASON_SHORT[effect.reason]}` : "";
  const left =
    effect.in_location !== null
      ? ` · noch ${effect.in_location} hier`
      : answer.variant
        ? ` · noch ${answer.variant.free_units} frei`
        : "";
  return `−${effect.quantity}${reason}${left}`;
}

/** `Nur 2 frei in R01-F01, 3 verlangt. Nichts ausgebucht.` */
function shortage(answer: ScanOut): string {
  const wanted = answer.quantity ?? 1;
  const place = answer.location?.code;
  const free = place ? answer.variant?.free_here : answer.variant?.free_units;
  if (free === undefined || free === null) {
    return MESSAGES.not_enough_free;
  }
  const where = place ? ` in ${place}` : "";
  return free === 0
    ? `Kein freies Stück${where}. Nichts ausgebucht.`
    : `Nur ${free} frei${where}, ${wanted} verlangt. Nichts ausgebucht.`;
}

/** `3 Teile` or `1 Teil`. */
export function partCount(count: number): string {
  return count === 1 ? "1 Teil" : `${count} Teile`;
}

/** One line saying what a scan did, in German. */
export function scanHeadline(answer: ScanOut): string {
  if (answer.undone) {
    return "Rückgängig gemacht.";
  }
  if (answer.outcome === "info") {
    return MESSAGES[answer.message];
  }
  if (answer.message === "put_away" && answer.effect?.reserved_for) {
    return `Eingelagert und gleich reserviert für ${answer.effect.reserved_for}.`;
  }
  if (answer.message === "picked" && answer.effect?.released_unit) {
    return "Kommissioniert. Das reservierte Stück bleibt im Lager.";
  }
  if (answer.message === "parts_stored" && answer.part_effect && answer.part) {
    return `${answer.part_effect.quantity} × ${answer.part.name} eingelagert.`;
  }
  if (answer.message === "booked_in" && answer.stock_effect) {
    return bookedIn(answer.stock_effect);
  }
  if (answer.message === "booked_out" && answer.stock_effect) {
    return bookedOut(answer, answer.stock_effect);
  }
  if (answer.message === "not_enough_free") {
    return shortage(answer);
  }
  return MESSAGES[answer.message];
}

/** The feedback a scan deserves: a bright tone, a low one, or a neutral click. */
export function scanFeedback(answer: ScanOut): "success" | "error" | "info" {
  if (answer.undone) {
    return "info";
  }
  if (answer.outcome === "applied" || answer.outcome === "selected") {
    return "success";
  }
  return answer.outcome === "info" ? "info" : "error";
}
