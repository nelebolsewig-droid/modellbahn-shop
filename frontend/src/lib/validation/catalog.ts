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

/** A paint as the shop shows it, like the backend: one line, first letter capital. */
export const colorName = z.string().transform((value, context) => {
  const tidy = value.trim().replace(/\s+/g, " ");
  if (Array.from(tidy).length > 40) {
    context.addIssue({ code: "custom", message: "Die Farbe darf höchstens 40 Zeichen lang sein." });
    return z.NEVER;
  }
  return tidy.charAt(0).toLocaleUpperCase("de-DE") + tidy.slice(1);
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

/** A number with at most one decimal place, German or English decimal mark ("22,5"). */
function oneDecimal(value: string): number | null {
  const text = value.trim().replace(",", ".");
  return /^\d+(\.\d)?$/.test(text) ? Number(text) : null;
}

/** The ratio of a scale, written as its denominator: "87" for 1:87, "22,5" for 1:22,5. */
export const scaleRatio = z.string().transform((value, context) => {
  const number = oneDecimal(value);
  if (number === null || number <= 1 || number > 1000) {
    context.addIssue({ code: "custom", message: "Bitte die Zahl nach „1:“ eingeben, z. B. 87 oder 22,5." });
    return z.NEVER;
  }
  return number;
});

/** A track gauge in mm; empty for scales without a track, e.g. road vehicles. */
export const optionalTrackGauge = z.string().transform((value, context) => {
  if (value.trim() === "") {
    return null;
  }
  const number = oneDecimal(value);
  if (number === null || number <= 0 || number >= 1000) {
    context.addIssue({ code: "custom", message: "Bitte die Spurweite in mm wie 16,5 eingeben oder leer lassen." });
    return z.NEVER;
  }
  return number;
});

/** Mirrors Scale.create in the catalogue domain. The code is fixed once saved. */
export const scaleSchema = z.object({
  code: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z0-9]{1,4}$/, "Ein bis vier Großbuchstaben oder Ziffern, z. B. H0 oder 124."),
  name: z
    .string()
    .trim()
    .min(1, "Bitte gib einen Namen ein, z. B. H0 oder 1:24.")
    .max(20, "Der Name darf höchstens 20 Zeichen lang sein."),
  ratio_denominator: scaleRatio,
  track_gauge_mm: optionalTrackGauge,
});

export type ScaleValues = z.input<typeof scaleSchema>;

/** Made to order: delivered within 1 to 52 weeks (catalog: domain/model.py, check_lead_time). */
export const LEAD_TIME_MAX_WEEKS = 52;
export const DEFAULT_LEAD_TIME = [1, 2] as const;

const weeks = (message: string) =>
  z
    .string()
    .trim()
    .regex(/^\d{1,2}$/, message)
    .transform(Number)
    .refine((value) => value >= 1 && value <= LEAD_TIME_MAX_WEEKS, { error: message });

export const leadTimeSchema = z
  .object({
    min: weeks(`Die Lieferzeit beginnt bei 1 bis ${LEAD_TIME_MAX_WEEKS} Wochen.`),
    max: weeks(`Die Lieferzeit endet bei 1 bis ${LEAD_TIME_MAX_WEEKS} Wochen.`),
  })
  .refine((value) => value.min <= value.max, { error: "„Von“ darf nicht nach „bis“ liegen.", path: ["max"] });
