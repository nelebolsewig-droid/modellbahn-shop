import type { ShippingCountryOut, TotalsOut } from "@/lib/api/generated/model";

/*
 * The same arithmetic as the backend (sales/domain/model.py), so the review page can
 * show the total for the chosen country before the order is sent. The backend checks
 * it again: a different total refuses the order (price_changed).
 */

const VAT_PERCENT = 19;

/** The VAT contained in a gross amount, rounded half up to the cent. */
export function includedVat(grossCents: number): number {
  return Math.floor((2 * grossCents * VAT_PERCENT + 100 + VAT_PERCENT) / (2 * (100 + VAT_PERCENT)));
}

/** Shipping for goods worth ``subtotalCents``; nothing to ship costs nothing. */
export function shippingCents(country: ShippingCountryOut, subtotalCents: number): number {
  return subtotalCents === 0 || subtotalCents >= country.free_from_cents ? 0 : country.rate_cents;
}

export function totalsFor(subtotalCents: number, country: ShippingCountryOut): TotalsOut {
  const shipping = shippingCents(country, subtotalCents);
  const total = subtotalCents + shipping;
  return {
    subtotal_cents: subtotalCents,
    shipping_cents: shipping,
    total_cents: total,
    tax_cents: includedVat(total),
  };
}

/** How much more until shipping is free; 0 when it already is (or the cart is empty). */
export function missingForFreeShipping(country: ShippingCountryOut, subtotalCents: number): number {
  return subtotalCents === 0 ? 0 : Math.max(0, country.free_from_cents - subtotalCents);
}
