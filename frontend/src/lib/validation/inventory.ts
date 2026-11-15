import { z } from "zod";

/*
 * The forms of the store in the Stellwerk; the limits are those of LocationPatchIn,
 * UnitsCreateIn and ScrapIn in the inventory API.
 */

const name = z.string().trim().max(60, "Bitte höchstens 60 Zeichen.");

export const locationRenameSchema = z.object({ name });
export type LocationRenameValues = z.input<typeof locationRenameSchema>;

export const UNITS_PER_BATCH_MAX = 200;

/** Einbuchen: the pieces lie in a place and come into the stock there at once. */
export const unitsCreateSchema = z.object({
  variant_id: z.string().min(1, "Bitte eine Ausführung wählen."),
  quantity: z.coerce
    .number<string>({ error: "Bitte eine Zahl eingeben." })
    .int("Bitte eine ganze Zahl eingeben.")
    .min(1, "Mindestens 1 Stück.")
    .max(UNITS_PER_BATCH_MAX, `Höchstens ${UNITS_PER_BATCH_MAX} Stück auf einmal.`),
  location_code: z.string().min(1, "Bitte den Platz wählen, in dem die Stücke liegen."),
  /** Print the model's labels right after (one per piece). */
  print: z.boolean(),
});
export type UnitsCreateValues = z.input<typeof unitsCreateSchema>;

export const SCRAP_REASONS = ["sold", "damaged", "missing", "mistake"] as const;

export const scrapSchema = z.object({
  // "" until one is chosen: the choice is required.
  reason: z.string().pipe(z.enum(SCRAP_REASONS, "Bitte einen Grund wählen.")),
  note: z.string().trim().max(200, "Bitte höchstens 200 Zeichen."),
});
export type ScrapValues = z.input<typeof scrapSchema>;
