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
});
export type CancelValues = z.input<typeof cancelSchema>;
