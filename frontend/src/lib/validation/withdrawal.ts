import { z } from "zod";

/*
 * Client-side mirror of the withdrawal function's input rules (backend: sales/domain/
 * withdrawals.py and api/schemas.py). The backend stays authoritative.
 */

const codePoints = (value: string): number => Array.from(value).length;

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export const withdrawalSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Bitte gib deinen Namen ein.")
    .refine((value) => codePoints(value) <= 200, { error: "Der Name darf höchstens 200 Zeichen lang sein." }),
  order_number: z
    .string()
    .trim()
    .min(1, "Bitte gib die Bestellnummer ein, z. B. MB-2026-00042.")
    .refine((value) => codePoints(value) <= 40, { error: "Die Bestellnummer darf höchstens 40 Zeichen lang sein." }),
  email: z.string().trim().regex(EMAIL, "Bitte gib eine gültige E-Mail-Adresse ein."),
  scope: z
    .string()
    .refine((value) => codePoints(value.trim()) <= 1000, {
      error: "Bitte fasse dich kürzer (höchstens 1000 Zeichen).",
    }),
});

export type WithdrawalValues = z.infer<typeof withdrawalSchema>;
