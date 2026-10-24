import { z } from "zod";

import { parseEuroToCents } from "@/lib/catalog/format";

/*
 * Client-side mirror of the catalogue's input rules (backend/src/modellbahn/modules/
 * catalog: domain/model.py and domain/text.py). The backend stays authoritative and
 * normalises (whitespace, line breaks); these give immediate feedback in German.
 */

const codePoints = (value: string): number => Array.from(value).length;

const bounded = (max: number, message: string) =>
  z.string().refine((value) => codePoints(value) <= max, { error: message });

export const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const productDetailsSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Bitte gib einen Namen ein.")
    .refine((value) => codePoints(value) <= 120, { error: "Der Name darf höchstens 120 Zeichen lang sein." }),
  slug: z
    .string()
    .trim()
    .min(1, "Bitte gib eine Adresse ein.")
    .max(80, "Die Adresse darf höchstens 80 Zeichen lang sein.")
    .regex(SLUG_PATTERN, "Nur Kleinbuchstaben, Ziffern und einzelne Bindestriche, z. B. stellwerk-altenau."),
  summary: bounded(280, "Der Kurztext darf höchstens 280 Zeichen lang sein."),
  description: bounded(10_000, "Die Beschreibung darf höchstens 10.000 Zeichen lang sein."),
  // Not "prototype": form libraries refuse that name to prevent prototype pollution.
  prototype_note: bounded(200, "Das Vorbild darf höchstens 200 Zeichen lang sein."),
  // "" stands for "no category" in the select.
  primary_category_id: z.string(),
  epoch_codes: z.array(z.string()),
});

export type ProductDetailsValues = z.input<typeof productDetailsSchema>;

/** A price field in euros ("49,90"); the result is cents. */
export const euroPrice = z.string().transform((value, context) => {
  const cents = parseEuroToCents(value);
  if (cents === null || cents > 10_000_000) {
    context.addIssue({ code: "custom", message: "Bitte einen Preis wie 49,90 eingeben." });
    return z.NEVER;
  }
  return cents;
});

/** An optional price: empty means "none". */
export const optionalEuroPrice = z.string().transform((value, context) => {
  if (value.trim() === "") {
    return null;
  }
  const cents = parseEuroToCents(value);
  if (cents === null || cents > 10_000_000) {
    context.addIssue({ code: "custom", message: "Bitte einen Preis wie 59,90 eingeben oder leer lassen." });
    return z.NEVER;
  }
  return cents;
});

/** Millimetres with one decimal, empty means unknown. */
export const optionalMillimetres = z.string().transform((value, context) => {
  const text = value.trim().replace(",", ".");
  if (text === "") {
    return null;
  }
  const number = Number(text);
  if (!/^\d+(\.\d+)?$/.test(text) || number <= 0 || number > 10_000) {
    context.addIssue({ code: "custom", message: "Bitte eine Länge in mm wie 112,5 eingeben." });
    return z.NEVER;
  }
  return Math.round(number * 10) / 10;
});

/** Grams as a whole number, empty means unknown. */
export const optionalGrams = z.string().transform((value, context) => {
  const text = value.trim();
  if (text === "") {
    return null;
  }
  const number = Number(text);
  if (!/^\d+$/.test(text) || number <= 0 || number > 100_000) {
    context.addIssue({ code: "custom", message: "Bitte ein Gewicht in ganzen Gramm eingeben." });
    return z.NEVER;
  }
  return number;
});
