import type { LampColor } from "@/components/ui/signal-lamp";
import type { StatusTone } from "@/components/ui/status-badge";
import type {
  PrinterDeskOut,
  PrinterStatus,
  PrintJobOut,
  PrintJobStatus,
  StaffRole,
  Technology,
} from "@/lib/api/generated/model";

/*
 * The printer hall as the Stellwerk shows it: German names for states and technologies,
 * the lamp of each printer, and how far a plate has come. The backend decides what is
 * allowed; this only presents it.
 */

export const PRINTER_STATUS_LABELS = {
  in_service: "In Betrieb",
  defective: "Defekt",
  in_repair: "In Reparatur",
  retired: "Ausgemustert",
} as const satisfies Record<PrinterStatus, string>;

/** The states within a sentence: "vorher in Betrieb", "D03 · defekt". */
export const PRINTER_STATE_PHRASES = {
  in_service: "in Betrieb",
  defective: "defekt",
  in_repair: "in Reparatur",
  retired: "ausgemustert",
} as const satisfies Record<PrinterStatus, string>;

export const TECHNOLOGY_LABELS = {
  fdm: "Filament",
  resin: "Resin",
} as const satisfies Record<Technology, string>;

/** Grams of filament, millilitres of resin. */
export const MATERIAL_UNITS = {
  fdm: "g",
  resin: "ml",
} as const satisfies Record<Technology, string>;

export const JOB_STATUS_LABELS = {
  queued: "Wartet",
  printing: "Druckt",
  post_processing: "Nachbearbeitung",
  done: "Fertig",
  failed: "Fehldruck",
  cancelled: "Abgebrochen",
} as const satisfies Record<PrintJobStatus, string>;

export const JOB_STATUS_TONES = {
  queued: "neutral",
  printing: "accent",
  post_processing: "warning",
  done: "success",
  failed: "danger",
  cancelled: "neutral",
} as const satisfies Record<PrintJobStatus, StatusTone>;

/** Owner and staff set up printers, parts and kits and plan the plates. */
export const MAY_PLAN: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

/**
 * What a printer is doing, for its lamp and its card:
 * printing (blue), ready with plates waiting (green), idle, down (defective: red, in
 * repair: yellow) or retired (off).
 */
export type DeskState = "printing" | "ready" | "idle" | "defective" | "in_repair" | "retired";

export function deskState(desk: PrinterDeskOut): DeskState {
  if (desk.status === "retired") return "retired";
  if (desk.status === "defective") return "defective";
  if (desk.status === "in_repair") return "in_repair";
  if (desk.printing !== null) return "printing";
  return desk.queue.length > 0 ? "ready" : "idle";
}

export const DESK_LAMPS = {
  printing: { color: "blue", label: "Druckt" },
  ready: { color: "green", label: "Bereit" },
  idle: { color: "green", label: "Frei" },
  defective: { color: "red", label: "Defekt" },
  in_repair: { color: "yellow", label: "In Reparatur" },
  retired: { color: "off", label: "Ausgemustert" },
} as const satisfies Record<DeskState, { color: LampColor; label: string }>;

/** "2 h 40", "4 h", "50 min". */
export function formatMinutes(minutes: number): string {
  const whole = Math.max(0, Math.round(minutes));
  const hours = Math.floor(whole / 60);
  const rest = whole % 60;
  if (hours === 0) return `${rest} min`;
  return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
}

export type PlateProgress = {
  /** Share of the planned time that has passed, 0 to 1. */
  fraction: number;
  elapsedMinutes: number;
  /** Minutes still to go; negative once it is overdue. */
  remainingMinutes: number;
  overdue: boolean;
  endsAt: Date;
};

/** How far a printing plate has come; null before it started or without a planned time. */
export function plateProgress(job: PrintJobOut, now: Date): PlateProgress | null {
  if (job.started_at === null || job.planned_minutes === null) return null;
  const started = new Date(job.started_at).getTime();
  const elapsed = Math.max(0, (now.getTime() - started) / 60_000);
  const remaining = job.planned_minutes - elapsed;
  return {
    fraction: Math.min(1, elapsed / job.planned_minutes),
    elapsedMinutes: elapsed,
    remainingMinutes: remaining,
    overdue: remaining < 0,
    endsAt: new Date(started + job.planned_minutes * 60_000),
  };
}

/** "4 × Dach, 8 × Schornstein": what lies on a plate, the first few parts. */
export function plateSummary(job: PrintJobOut, shown = 3): string {
  const parts = job.lines.slice(0, shown).map((line) => `${line.quantity} × ${line.part.name}`);
  const more = job.lines.length - shown;
  return more > 0 ? `${parts.join(", ")} und ${more} weitere` : parts.join(", ");
}

/** "seit 3 Tagen", "seit 2 Stunden", "seit eben", for how long a state has lasted. */
export function sinceText(since: Date, now: Date): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - since.getTime()) / 60_000));
  if (minutes < 2) return "seit eben";
  if (minutes < 60) return `seit ${minutes} Minuten`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "seit einer Stunde" : `seit ${hours} Stunden`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "seit einem Tag" : `seit ${days} Tagen`;
}

/** "Druck 17" */
export function jobTitle(job: Pick<PrintJobOut, "number">): string {
  return `Druck ${job.number}`;
}

/**
 * The plate's printing time from the parts' print data, like the backend estimates it:
 * on filament every part adds its share of a full plate, on resin the slowest part sets
 * the time. Null while a part has no plate time.
 */
export function estimateMinutes(
  technology: Technology,
  lines: readonly { plateMinutes: number | null; perPlate: number; quantity: number }[],
): number | null {
  if (lines.length === 0 || lines.some((line) => line.plateMinutes === null)) return null;
  if (technology === "resin") return Math.max(...lines.map((line) => line.plateMinutes ?? 0));
  const total = lines.reduce((sum, line) => sum + ((line.plateMinutes ?? 0) / line.perPlate) * line.quantity, 0);
  return Math.max(1, Math.ceil(total - 1e-9));
}
