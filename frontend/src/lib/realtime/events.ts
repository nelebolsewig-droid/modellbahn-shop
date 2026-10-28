import { z } from "zod";

import type { RealtimeEventData } from "@/lib/api/generated/model";

/** SSE endpoint of the admin area (staff session only). */
export const ADMIN_EVENTS_URL = "/api/v1/admin/events";

/**
 * Event types the API pushes to the "staff" audience, with their German names.
 * EventSource only delivers named events that have a listener, so a new type
 * appears in the feed once it is listed here.
 */
export const STAFF_EVENT_LABELS = {
  "identity.customer.registered": "Neue Registrierung",
  "identity.account.email_verified": "E-Mail-Adresse bestätigt",
  "catalog.product.published": "Produkt veröffentlicht",
  "catalog.product.archived": "Produkt archiviert",
  "media.asset.ready": "Foto verarbeitet",
  "media.asset.failed": "Foto unbrauchbar",
  "sales.order.placed": "Neue Bestellung",
  "sales.order.paid": "Bestellung bezahlt",
  "sales.order.shipped": "Bestellung versendet",
  "sales.order.cancelled": "Bestellung storniert",
  "inventory.allocation.backordered": "Stück muss gefertigt werden",
  "site.fair.announced": "Messe angekündigt",
} as const satisfies Record<string, string>;

/** The media events, for pages that wait for their uploads (the product editor). */
export const MEDIA_EVENT_TYPES = ["media.asset.ready", "media.asset.failed"] as const;

/** The order events, for the order pages of the admin area. */
export const ORDER_EVENT_TYPES = [
  "sales.order.placed",
  "sales.order.paid",
  "sales.order.shipped",
  "sales.order.cancelled",
] as const;

/**
 * The stock events, for the stock pages, the scanner and the pick list. Every scan
 * moves a unit, so these stay out of the feed on the start page; only a piece that
 * has to be made shows up there.
 */
export const INVENTORY_EVENT_TYPES = [
  "inventory.stock.changed",
  "inventory.location.changed",
  "inventory.allocation.backordered",
] as const;

export type StaffEventType = keyof typeof STAFF_EVENT_LABELS;

export const STAFF_EVENT_TYPES = Object.keys(STAFF_EVENT_LABELS) as StaffEventType[];

/** The JSON in each message's `data:` line (RealtimeEventData in openapi.json). */
const realtimeEventSchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  occurred_at: z.iso.datetime({ offset: true }),
  data: z.record(z.string(), z.unknown()),
  truncated: z.boolean(),
}) satisfies z.ZodType<RealtimeEventData>;

/** Public payload of the identity events (display name, never the e-mail address). */
const accountPayloadSchema = z.object({
  account_id: z.string(),
  display_name: z.string(),
});

/** Public payload of the catalogue events. */
const productPayloadSchema = z.object({ product_id: z.string(), name: z.string() });

/** Public payload of the fair events. */
const fairPayloadSchema = z.object({ fair_id: z.string(), name: z.string() });

/** Public payload of the order events: number and total, never the customer's data. */
const orderPayloadSchema = z.object({
  order_id: z.string(),
  number: z.string(),
  total_cents: z.number().int(),
});

const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

/** Public payload of the media events: the page fetches the asset itself. */
const assetPayloadSchema = z.object({ asset_id: z.string() });

/** Public payload of the stock events: codes and ids, never who did it. */
const stockPayloadSchema = z.object({
  variant_id: z.string().optional(),
  order_id: z.string().nullable().optional(),
  unit_code: z.string().optional(),
  location_code: z.string().nullable().optional(),
  previous_location_code: z.string().nullable().optional(),
  code: z.string().optional(),
});

export type FeedEntry = {
  id: string;
  type: string;
  label: string;
  occurredAt: Date;
  /** Who the event is about, when the payload names an account. */
  account?: { id: string; displayName: string };
  /** What the event is about otherwise, e.g. the product's name. */
  subject?: string;
  truncated: boolean;
};

function labelFor(type: string): string {
  return Object.hasOwn(STAFF_EVENT_LABELS, type)
    ? STAFF_EVENT_LABELS[type as StaffEventType]
    : type;
}

/** Turns one SSE message into a feed entry; null if the message is malformed. */
export function parseFeedEntry(raw: string): FeedEntry | null {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return null;
  }
  const parsed = realtimeEventSchema.safeParse(json);
  if (!parsed.success) {
    return null;
  }
  const event = parsed.data;
  const account = accountPayloadSchema.safeParse(event.data);
  const product = productPayloadSchema.safeParse(event.data);
  const order = orderPayloadSchema.safeParse(event.data);
  const fair = fairPayloadSchema.safeParse(event.data);
  return {
    id: event.id,
    type: event.type,
    label: labelFor(event.type),
    occurredAt: new Date(event.occurred_at),
    ...(account.success && {
      account: { id: account.data.account_id, displayName: account.data.display_name },
    }),
    ...(product.success && { subject: product.data.name }),
    ...(fair.success && { subject: fair.data.name }),
    ...(order.success && {
      subject: `${order.data.number} · ${euro.format(order.data.total_cents / 100)}`,
    }),
    truncated: event.truncated,
  };
}

/** Type and payload of one SSE message, if it is an event and its payload fits `schema`. */
function eventOf<T>(raw: string, schema: z.ZodType<T>): { type: string; payload: T } | null {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return null;
  }
  const parsed = realtimeEventSchema.safeParse(json);
  if (!parsed.success) {
    return null;
  }
  const payload = schema.safeParse(parsed.data.data);
  return payload.success ? { type: parsed.data.type, payload: payload.data } : null;
}

/** The asset an SSE message of the media events is about; null for anything else. */
export function assetIdOf(raw: string): string | null {
  return eventOf(raw, assetPayloadSchema)?.payload.asset_id ?? null;
}

/** The order an SSE message of the order events is about, and what happened; null for anything else. */
export function orderEventOf(raw: string): { type: string; orderId: string } | null {
  const event = eventOf(raw, orderPayloadSchema);
  return event === null ? null : { type: event.type, orderId: event.payload.order_id };
}

export type StockEvent = {
  type: string;
  variantId: string | null;
  orderId: string | null;
  unitCode: string | null;
  /** The locations the event touched: where a unit went and came from, or the changed location. */
  locationCodes: string[];
};

/** What an SSE message of the stock events is about; null for anything else. */
export function stockEventOf(raw: string): StockEvent | null {
  const event = eventOf(raw, stockPayloadSchema);
  if (event === null || !event.type.startsWith("inventory.")) {
    return null;
  }
  const { payload } = event;
  const locationCodes = [payload.location_code, payload.previous_location_code, payload.code].filter(
    (code): code is string => typeof code === "string" && code !== "",
  );
  return {
    type: event.type,
    variantId: payload.variant_id ?? null,
    orderId: payload.order_id ?? null,
    unitCode: payload.unit_code ?? null,
    locationCodes,
  };
}

/** Newest first, without duplicates (a replay after reconnecting may repeat events). */
export function mergeFeed(entries: readonly FeedEntry[], entry: FeedEntry, limit: number): FeedEntry[] {
  if (entries.some((existing) => existing.id === entry.id)) {
    return [...entries];
  }
  // Event ids are UUIDv7 and therefore ordered by time.
  return [entry, ...entries].sort((a, b) => (a.id < b.id ? 1 : -1)).slice(0, limit);
}
