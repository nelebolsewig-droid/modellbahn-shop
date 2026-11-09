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
