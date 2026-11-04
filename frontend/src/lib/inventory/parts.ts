import type { AssemblyPartOut, PartHistoryEntryOut, ReceiptOut } from "@/lib/api/generated/model";

import { formatUnitCode } from "./codes";
import { partCount } from "./labels";

/*
 * The parts store in words and shapes: the receiving area as one delivery note per
 * plate, the parts journal in German, and how far the stock covers an assembly.
 */

export type ReceivingSlip = {
  key: string;
  number: number | null;
  printerCode: string | null;
  finishedAt: string | null;
  receipts: ReceiptOut[];
  /** Parts of the plate still waiting for a box. */
  open: number;
};

/** The receiving area as delivery notes: one per plate, the oldest plate first. */
export function receivingSlips(receipts: readonly ReceiptOut[]): ReceivingSlip[] {
  const slips = new Map<string, ReceivingSlip>();
  for (const receipt of receipts) {
    const key = receipt.print_job?.job_id ?? receipt.id;
    const slip = slips.get(key) ?? {
      key,
      number: receipt.print_job?.number ?? null,
      printerCode: receipt.print_job?.printer_code ?? null,
      finishedAt: receipt.print_job?.finished_at ?? receipt.created_at,
      receipts: [],
      open: 0,
    };
    slip.receipts.push(receipt);
    slip.open += receipt.open;
    slips.set(key, slip);
  }
  return [...slips.values()].sort((a, b) => (a.finishedAt ?? "").localeCompare(b.finishedAt ?? ""));
}

function plate(number: number | null): string {
  return number === null ? "dem Eingang" : `Druck ${number}`;
}

/** One line of a part's journal: how many went where. */
export function partMovementText(entry: PartHistoryEntryOut): string {
  const count = partCount(entry.quantity);
  switch (entry.reason) {
    case "receive":
      return `${count} aus ${plate(entry.print_job_number)} in ${entry.to_location_code ?? "eine Box"}`;
    case "assemble":
      return `${count} aus ${entry.from_location_code ?? "einer Box"} in ${entry.unit_code ? formatUnitCode(entry.unit_code) : "eine Einheit"}`;
    case "count":
      return entry.to_location_code
        ? `${count} mehr gezählt in ${entry.to_location_code}`
        : `${count} weniger gezählt in ${entry.from_location_code ?? "einer Box"}`;
    case "write_off":
      return `${count} aus ${plate(entry.print_job_number)} ausgebucht`;
    case "undo":
      return `${count} aus ${entry.from_location_code ?? "der Box"} zurück in den Wareneingang`;
  }
}

/** The share of the needed parts that lies in stock (1 when nothing is missing). */
export function coverage(part: Pick<AssemblyPartOut, "needed" | "available">): number {
  return part.needed === 0 ? 1 : Math.min(1, part.available / part.needed);
}

/** How full a box looks next to the fullest box of the same part (at least a sliver). */
export function binLevel(quantity: number, fullest: number): number {
  if (quantity <= 0 || fullest <= 0) {
    return 0;
  }
  return Math.max(0.12, Math.min(1, quantity / fullest));
}
