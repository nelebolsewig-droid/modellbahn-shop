import { z } from "zod";

import { normalizePostalCode, SHIPPING_COUNTRIES, shippingCountry, type ShippingCountry } from "@/lib/sales/countries";

/*
 * Client-side mirror of the sales module's address rules (backend/src/modellbahn/
 * modules/sales/domain/model.py). The backend stays authoritative; these give
 * immediate feedback in German. Field names are the API's.
 */

export { SHIPPING_COUNTRIES, type ShippingCountry };

/** Germany's and Austria's codes are plain digits; the others get an example. */
const DIGITS_ONLY: Partial<Record<ShippingCountry, string>> = {
  DE: "Bitte gib eine fünfstellige Postleitzahl ein.",
  AT: "Bitte gib eine vierstellige Postleitzahl ein.",
};

const collapse = (value: string): string => value.split(/\s+/u).filter(Boolean).join(" ");

const text = (missing: string, max: number) =>
  z
    .string()
    .transform(collapse)
    .pipe(z.string().min(1, missing).max(max, `Bitte höchstens ${max} Zeichen.`));

const email = z
  .string()
  .trim()
  .min(1, "Bitte gib deine E-Mail-Adresse ein.")
  .pipe(z.email("Bitte gib eine gültige E-Mail-Adresse ein."));

const addressFields = {
  recipient: text("Bitte gib den Namen für das Paket ein.", 80),
  street: text("Bitte gib Straße und Hausnummer ein.", 100),
  postal_code: z.string().transform(normalizePostalCode),
  city: text("Bitte gib den Ort ein.", 60),
  country_code: z.enum(SHIPPING_COUNTRIES, "Dorthin liefern wir leider nicht."),
};

function checkPostalCode(
  value: { postal_code: string; country_code: ShippingCountry },
  context: z.RefinementCtx,
): void {
  const country = shippingCountry(value.country_code);
  if (country && !country.postal.test(value.postal_code)) {
    const message =
      DIGITS_ONLY[value.country_code] ?? `Bitte gib eine Postleitzahl aus ${country.name} ein, z. B. ${country.example}.`;
    context.addIssue({ code: "custom", path: ["postal_code"], message });
  }
}

export type AddressValues = {
  recipient: string;
  street: string;
  postal_code: string;
  city: string;
  country_code: ShippingCountry;
};

export const EMPTY_ADDRESS: AddressValues = {
  recipient: "",
  street: "",
  postal_code: "",
  city: "",
  country_code: "DE",
};

/** An entry of the address book: an address with an optional label. */
export const bookEntrySchema = z
  .object({
    label: z
      .string()
      .transform(collapse)
      .pipe(z.string().max(40, "Bitte höchstens 40 Zeichen.")),
    ...addressFields,
    is_default: z.boolean(),
  })
  .superRefine(checkPostalCode);
export type BookEntryValues = z.input<typeof bookEntrySchema>;

/**
 * The checkout form. What it needs depends on who orders and where to: guests give
 * an e-mail address, a new address needs every field, an entry of the address book
 * none of them.
 */
export type CheckoutNeeds = { email: boolean; address: boolean };

export function checkoutSchema(needs: CheckoutNeeds) {
  return z
    .object({
      email: needs.email ? email : z.string(),
      recipient: needs.address ? addressFields.recipient : z.string(),
      street: needs.address ? addressFields.street : z.string(),
      postal_code: addressFields.postal_code,
      city: needs.address ? addressFields.city : z.string(),
      country_code: addressFields.country_code,
      save_address: z.boolean(),
    })
    .superRefine((value, context) => {
      if (needs.address) {
        checkPostalCode(value, context);
      }
    });
}
export type CheckoutValues = z.input<ReturnType<typeof checkoutSchema>>;
