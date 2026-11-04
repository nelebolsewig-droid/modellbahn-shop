import type { StatusTone } from "@/components/ui/status-badge";
import type {
  LocationKind,
  MovementReason,
  PartMovementReason,
  PieceState,
  ScanMode,
  ScanOut,
  ScanOutcome,
  ScanOutMessage,
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

export const UNIT_STATUS_TONES: Readonly<Record<UnitStatus, StatusTone>> = {
  labeled: "warning",
  in_stock: "success",
  allocated: "accent",
  picked: "accent",
  shipped: "neutral",
  scrapped: "danger",
};

export const PIECE_STATE_LABELS: Readonly<Record<PieceState, string>> = {
  backordered: "In Fertigung",
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
  unit: "Einheit",
  location: "Lagerplatz",
  variant: "Artikel",
  location_selected: "Lagerplatz gewählt. Jetzt die Ware scannen.",
  location_required: "Erst den Lagerplatz scannen, dann die Ware.",
  location_unknown: "Den gewählten Lagerplatz gibt es nicht mehr. Bitte neu scannen.",
  holds_no_goods: "Hier kommt keine Ware hinein: nur Fächer, Boxen und Ablagen.",
  already_there: "Liegt schon hier.",
  unit_gone: "Diese Einheit ist versendet oder ausgebucht.",
  unit_picked: "Diese Einheit ist für eine Bestellung kommissioniert.",
  put_away: "Eingelagert.",
  move: "Umgelagert.",
  no_unit_to_store: "Kein unverbuchtes Stück dieses Artikels. Bitte den Einheiten-Code scannen.",
  scan_unit_label: "Bitte das Etikett der Ware scannen.",
  order_unknown: "Diese Bestellung gibt es nicht. Bitte neu wählen.",
  order_not_pickable: "Diese Bestellung ist nicht bezahlt oder noch nicht zugeteilt.",
  picked: "Kommissioniert.",
  already_picked: "Schon kommissioniert.",
  reserved_for_other_order: "Falsches Stück: Es ist für eine andere Bestellung reserviert.",
  variant_complete: "Von diesem Artikel ist schon alles kommissioniert.",
  not_in_order: "Falscher Artikel: Er gehört nicht zu dieser Bestellung.",
  unit_not_stored: "Dieses Stück ist noch nicht eingelagert.",
  variant_not_in_stock: "Kein Stück dieses Artikels im Lager.",
  part: "Teil",
  parts_stored: "Teile eingelagert.",
  no_parts_to_store: "Von diesem Teil wartet nichts im Wareneingang.",
};

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
