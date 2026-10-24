import { describe, expect, it } from "vitest";

import { assetIdOf, mergeFeed, parseFeedEntry, STAFF_EVENT_TYPES, type FeedEntry } from "./events";

function message(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    id: "0192f1c4-7a3e-7cc2-9d5e-1b2c3d4e5f60",
    type: "identity.customer.registered",
    occurred_at: "2026-10-22T12:32:05.123456Z",
    data: { account_id: "0192f1c4-0000-7000-8000-000000000001", display_name: "Erika Mustermann" },
    truncated: false,
    ...overrides,
  });
}

function entry(id: string): FeedEntry {
  return { id, type: "t", label: "t", occurredAt: new Date(0), truncated: false };
}

describe("parseFeedEntry", () => {
  it("reads a staff event with its German label and the account's display name", () => {
    expect(parseFeedEntry(message())).toEqual({
      id: "0192f1c4-7a3e-7cc2-9d5e-1b2c3d4e5f60",
      type: "identity.customer.registered",
      label: "Neue Registrierung",
      occurredAt: new Date("2026-10-22T12:32:05.123Z"),
      account: { id: "0192f1c4-0000-7000-8000-000000000001", displayName: "Erika Mustermann" },
      truncated: false,
    });
  });

  it("labels a verified address", () => {
    expect(parseFeedEntry(message({ type: "identity.account.email_verified" }))?.label).toBe(
      "E-Mail-Adresse bestätigt",
    );
  });

  it("shows an unknown event type as it is, without an account if the payload has none", () => {
    const parsed = parseFeedEntry(message({ type: "sales.order.placed", data: { sku: "1" } }));
    expect(parsed?.label).toBe("sales.order.placed");
    expect(parsed?.account).toBeUndefined();
    expect(parsed?.subject).toBeUndefined();
  });

  it("names the product of a catalogue event", () => {
    const parsed = parseFeedEntry(
      message({ type: "catalog.product.published", data: { product_id: "p1", name: "Stellwerk Altenau" } }),
    );
    expect(parsed?.label).toBe("Produkt veröffentlicht");
    expect(parsed?.subject).toBe("Stellwerk Altenau");
    expect(parsed?.account).toBeUndefined();
  });

  it.each([
    ["not json", "{"],
    ["no id", message({ id: "" })],
    ["bad timestamp", message({ occurred_at: "gestern" })],
    ["data not an object", message({ data: "x" })],
  ])("ignores a malformed message (%s)", (_, raw) => {
    expect(parseFeedEntry(raw)).toBeNull();
  });

  it("listens to every staff event type", () => {
    expect(STAFF_EVENT_TYPES).toEqual([
      "identity.customer.registered",
      "identity.account.email_verified",
      "catalog.product.published",
      "catalog.product.archived",
      "media.asset.ready",
      "media.asset.failed",
    ]);
  });
});

describe("assetIdOf", () => {
  it("reads the asset of a media event", () => {
    expect(assetIdOf(message({ type: "media.asset.ready", data: { asset_id: "a1" } }))).toBe("a1");
  });

  it.each([["not json", "{"], ["no asset", message()], ["malformed", message({ id: "" })]])(
    "is null for anything else (%s)",
    (_, raw) => {
      expect(assetIdOf(raw)).toBeNull();
    },
  );
});

describe("mergeFeed", () => {
  it("puts the newest event first, ordered by UUIDv7", () => {
    const merged = mergeFeed([entry("0192-b"), entry("0192-a")], entry("0192-c"), 10);
    expect(merged.map((item) => item.id)).toEqual(["0192-c", "0192-b", "0192-a"]);
  });

  it("sorts an event replayed out of order into place", () => {
    const merged = mergeFeed([entry("0192-c"), entry("0192-a")], entry("0192-b"), 10);
    expect(merged.map((item) => item.id)).toEqual(["0192-c", "0192-b", "0192-a"]);
  });

  it("ignores an event it already shows (replay after a reconnect)", () => {
    const merged = mergeFeed([entry("0192-a")], entry("0192-a"), 10);
    expect(merged).toHaveLength(1);
  });

  it("keeps at most `limit` entries", () => {
    const merged = mergeFeed([entry("0192-b"), entry("0192-a")], entry("0192-c"), 2);
    expect(merged.map((item) => item.id)).toEqual(["0192-c", "0192-b"]);
  });
});
