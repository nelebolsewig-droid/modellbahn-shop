import { z } from "zod";

import { SEGMENT_PATTERN } from "@/lib/inventory/locations";

/*
 * The forms of the store in the Stellwerk; the limits are those of LocationCreateIn,
 * LocationPatchIn, UnitsCreateIn and ScrapIn in the inventory API.
 */

const name = z.string().trim().max(60, "Bitte höchstens 60 Zeichen.");

export const locationCreateSchema = z.object({
  segment: z
    .string()
    .trim()
    .toUpperCase()
    .regex(SEGMENT_PATTERN, "1 bis 8 Buchstaben oder Ziffern, z. B. R02 oder F04."),
  kind: z.enum(["site", "shelf", "compartment", "box", "staging"]),
  name,
});
export type LocationCreateValues = z.input<typeof locationCreateSchema>;

export const locationRenameSchema = z.object({ name });
export type LocationRenameValues = z.input<typeof locationRenameSchema>;

export const UNITS_PER_BATCH_MAX = 200;

export const unitsCreateSchema = z.object({
  variant_id: z.string().min(1, "Bitte eine Ausführung wählen."),
  quantity: z.coerce
    .number<string>({ error: "Bitte eine Zahl eingeben." })
    .int("Bitte eine ganze Zahl eingeben.")
    .min(1, "Mindestens 1 Stück.")
    .max(UNITS_PER_BATCH_MAX, `Höchstens ${UNITS_PER_BATCH_MAX} Stück auf einmal.`),
  // "" stands for "put away later, by scanning".
  location_code: z.string(),
});
export type UnitsCreateValues = z.input<typeof unitsCreateSchema>;

export const scrapSchema = z.object({
  note: z.string().trim().max(200, "Bitte höchstens 200 Zeichen."),
});
export type ScrapValues = z.input<typeof scrapSchema>;
