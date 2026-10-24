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
} as const satisfies Record<string, string>;

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

export type FeedEntry = {
  id: string;
  type: string;
  label: string;
  occurredAt: Date;
  /** Who the event is about, when the payload names an account. */
  account?: { id: string; displayName: string };
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
  const payload = accountPayloadSchema.safeParse(event.data);
  return {
    id: event.id,
    type: event.type,
    label: labelFor(event.type),
    occurredAt: new Date(event.occurred_at),
    ...(payload.success && {
      account: { id: payload.data.account_id, displayName: payload.data.display_name },
    }),
    truncated: event.truncated,
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
