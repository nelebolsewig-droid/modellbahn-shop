import { z } from "zod";

/*
 * Client-side mirror of the site's input rules (backend/src/modellbahn/modules/site:
 * domain/model.py and api/schemas.py). The backend stays authoritative and tidies
 * spaces and line breaks; these give immediate feedback in German.
 */

const codePoints = (value: string): number => Array.from(value).length;

const bounded = (max: number, message: string) =>
  z.string().refine((value) => codePoints(value) <= max, { error: message });

/** At most this many days, like FAIR_DAYS_MAX in the backend. */
export const FAIR_DAYS_MAX = 14;

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const URL_PATTERN = /^https?:\/\/[^\s/$.?#][^\s]*$/i;

const day = (message: string) => z.string().regex(DAY, message);

export const fairSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Bitte gib den Namen der Messe ein.")
      .refine((value) => codePoints(value) <= 120, { error: "Der Name darf höchstens 120 Zeichen lang sein." }),
    starts_on: day("Bitte wähle den ersten Tag."),
    ends_on: day("Bitte wähle den letzten Tag."),
    venue: bounded(120, "Der Ort darf höchstens 120 Zeichen lang sein."),
    street: bounded(120, "Die Straße darf höchstens 120 Zeichen lang sein."),
    postal_code: bounded(10, "Die Postleitzahl darf höchstens 10 Zeichen lang sein."),
    city: z
      .string()
      .trim()
      .min(1, "Bitte gib die Stadt ein.")
      .refine((value) => codePoints(value) <= 80, { error: "Die Stadt darf höchstens 80 Zeichen lang sein." }),
    booth: bounded(60, "Der Stand darf höchstens 60 Zeichen lang sein."),
    hours: bounded(200, "Die Öffnungszeiten dürfen höchstens 200 Zeichen lang sein."),
    website_url: z
      .string()
      .trim()
      .refine((value) => value === "" || (value.length <= 300 && URL_PATTERN.test(value)), {
        error: "Bitte eine vollständige Adresse mit https://, z. B. https://www.messe.de.",
      }),
    note: bounded(500, "Der Hinweis darf höchstens 500 Zeichen lang sein."),
    published: z.boolean(),
  })
  .superRefine((values, context) => {
    if (!DAY.test(values.starts_on) || !DAY.test(values.ends_on)) {
      return;
    }
    if (values.ends_on < values.starts_on) {
      context.addIssue({ code: "custom", path: ["ends_on"], message: "Der letzte Tag liegt vor dem ersten." });
      return;
    }
    const days = (Date.parse(values.ends_on) - Date.parse(values.starts_on)) / 86_400_000;
    if (days >= FAIR_DAYS_MAX) {
      context.addIssue({
        code: "custom",
        path: ["ends_on"],
        message: `Eine Messe dauert hier höchstens ${FAIR_DAYS_MAX} Tage.`,
      });
    }
  });

export type FairValues = z.input<typeof fairSchema>;

export const EMPTY_FAIR: FairValues = {
  name: "",
  starts_on: "",
  ends_on: "",
  venue: "",
  street: "",
  postal_code: "",
  city: "",
  booth: "",
  hours: "",
  website_url: "",
  note: "",
  published: false,
};

export const fairNewsSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Bitte gib deine E-Mail-Adresse ein.")
    .pipe(z.email("Bitte gib eine gültige E-Mail-Adresse ein.")),
  consent: z.boolean().refine((value) => value, {
    error: "Bitte setz den Haken, damit wir dir die Messe-Post schicken dürfen.",
  }),
});

export type FairNewsValues = z.input<typeof fairNewsSchema>;
