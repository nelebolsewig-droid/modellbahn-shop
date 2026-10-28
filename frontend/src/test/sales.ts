import type { CartLineOut, CartOut, OrderOut, ShippingCountryOut } from "@/lib/api/generated/model";

export const GERMANY: ShippingCountryOut = {
  code: "DE",
  name: "Deutschland",
  rate_cents: 490,
  free_from_cents: 5000,
};
export const AUSTRIA: ShippingCountryOut = {
  code: "AT",
  name: "Österreich",
  rate_cents: 990,
  free_from_cents: 10000,
};

export function cartLine(overrides: Partial<CartLineOut> = {}): CartLineOut {
  return {
    variant_id: "v-painted",
    product_slug: "stellwerk-altenau",
    product_name: "Stellwerk Altenau",
    scale_code: "H0",
    scale_name: "H0",
    finish_code: "painted",
    finish_name: "bemalt",
    sku: "MB-000006-H0-B",
    quantity: 1,
    unit_price_cents: 7990,
    compare_at_price_cents: null,
    line_total_cents: 7990,
    available: true,
    availability: "in_stock",
    free_units: 5,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
    image: null,
    ...overrides,
  };
}

/** A cart as the API answers, with totals computed like the backend does (shipping to DE). */
export function cartOut(...lines: CartLineOut[]): CartOut {
  const subtotal = lines.filter((l) => l.available).reduce((sum, l) => sum + l.line_total_cents, 0);
  const shipping = subtotal === 0 || subtotal >= GERMANY.free_from_cents ? 0 : GERMANY.rate_cents;
  const total = subtotal + shipping;
  return {
    lines,
    item_count: lines.filter((l) => l.available).reduce((sum, l) => sum + l.quantity, 0),
    totals: {
      subtotal_cents: subtotal,
      shipping_cents: shipping,
      total_cents: total,
      tax_cents: Math.floor((38 * total + 119) / 238),
    },
    shipping_country: GERMANY,
    ready_for_checkout: lines.length > 0 && lines.every((l) => l.available),
    countries: [GERMANY, AUSTRIA],
  };
}

export function orderOut(overrides: Partial<OrderOut> = {}): OrderOut {
  return {
    number: "MB-2026-00042",
    public_token: "status-token",
    status: "pending_payment",
    email: "erika@example.de",
    shipping_address: {
      recipient: "Erika Mustermann",
      street: "Bahnhofstraße 12",
      postal_code: "38707",
      city: "Altenau",
      country_code: "DE",
      country_name: "Deutschland",
    },
    lines: [
      {
        variant_id: "v-painted",
        product_slug: "stellwerk-altenau",
        sku: "MB-000006-H0-B",
        title: "Stellwerk Altenau · H0 · bemalt",
        scale_code: "H0",
        finish_code: "painted",
        unit_price_cents: 7990,
        quantity: 1,
        line_total_cents: 7990,
        image: null,
      },
    ],
    totals: { subtotal_cents: 7990, shipping_cents: 0, total_cents: 7990, tax_cents: 1276 },
    payments: [],
    placed_at: "2026-10-25T09:00:00Z",
    paid_at: null,
    shipped_at: null,
    cancelled_at: null,
    cancel_reason: null,
    carrier: "",
    tracking_number: "",
    payment_due_at: "2026-10-26T09:00:00Z",
    ...overrides,
  };
}
