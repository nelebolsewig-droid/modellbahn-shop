import type { SliceFileOut } from "@/lib/api/generated/model";

/** What of a sliced file goes to the API: its head, never the layers (ADR 0037). */
export const SLICE_HEAD_BYTES = 512 * 1024;

/** Sliced files the reader knows; the picker offers only these. */
export const SLICE_FILE_ACCEPT = ".ctb,.goo,.cbddlp";

/** The first bytes of a file, Base64, as the API reads them. */
export async function sliceHead(file: Blob): Promise<string> {
  const bytes = new Uint8Array(
    await file.slice(0, SLICE_HEAD_BYTES).arrayBuffer(),
  );
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

/** The part's print data from a plate: the plate's time and layers, the resin of one part. */
export function plateValues(plate: SliceFileOut, partsPerPlate: number) {
  const parts =
    Number.isFinite(partsPerPlate) && partsPerPlate >= 1
      ? Math.round(partsPerPlate)
      : 1;
  return {
    plate_minutes: String(Math.max(1, Math.round(plate.print_seconds / 60))),
    layer_height_um: String(plate.layer_height_um),
    material_per_part: String(
      Math.round((plate.volume_ml / parts) * 100) / 100,
    ).replace(".", ","),
  };
}

/** „2 h 44 min“ */
export function printDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return hours > 0 ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}
