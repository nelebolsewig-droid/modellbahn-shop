import { z } from "zod";

/*
 * The forms of the order desk in the Stellwerk; the limits are those of ShipIn and
 * CancelIn in the sales API.
 */

const optionalText = (max: number) =>
  z.string().trim().max(max, `Bitte höchstens ${max} Zeichen.`);

export const shipSchema = z.object({
  carrier: optionalText(40),
  tracking_number: optionalText(40),
});
export type ShipValues = z.input<typeof shipSchema>;

export const cancelSchema = z.object({
  note: optionalText(300),
  /** Refunded in the SumUp account already: the shop records it and asks SumUp no more. */
  refunded_by_hand: z.boolean(),
});
export type CancelValues = z.input<typeof cancelSchema>;

/** ``de89 3704 …`` → ``DE893704…``, as the API stores it. */
export function normaliseIban(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

/** Format and check digits (ISO 13616, modulo 97), the same test the API makes. */
export function ibanIsValid(value: string): boolean {
  const iban = normaliseIban(value);
  if (!/^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/.test(iban)) {
    return false;
  }
  const digits = (iban.slice(4) + iban.slice(0, 4)).replace(/[A-Z]/g, (char) => String(char.charCodeAt(0) - 55));
  let rest = 0;
  for (const digit of digits) {
    rest = (rest * 10 + Number(digit)) % 97;
  }
  return rest === 1;
}

/** Where a bank transfer's refund goes back to (ADR 0040), from the bank statement. */
export const repaymentAccountSchema = z.object({
  holder: z.string().trim().min(1, "Bitte den Namen eintragen.").max(70, "Bitte höchstens 70 Zeichen."),
  iban: z
    .string()
    .trim()
    .min(1, "Bitte die IBAN eintragen.")
    .refine(ibanIsValid, "Diese IBAN stimmt nicht. Bitte noch einmal mit dem Kontoauszug vergleichen."),
});
export type RepaymentAccountValues = z.input<typeof repaymentAccountSchema>;
