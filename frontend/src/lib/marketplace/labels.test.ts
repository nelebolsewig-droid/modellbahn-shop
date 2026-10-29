import { describe, expect, it } from "vitest";

import type { EbayStatusOut, ListingOut } from "@/lib/api/generated/model";

import { isReady, listingState, priceWithMarkup } from "./labels";

function listing(overrides: Partial<ListingOut> = {}): ListingOut {
  return {
    id: "l1",
    product_id: "p1",
    scale_code: "H0",
    group_key: "MB-000042-H0",
    wanted: true,
    status: "active",
    external_id: "110012345678",
    url: null,
    needs_sync: false,
    error_code: null,
    error_message: "",
    synced_at: "2026-10-29T08:00:00Z",
    updated_at: "2026-10-29T08:00:00Z",
    items: [],
    ...overrides,
  };
}

describe("listingState", () => {
  it("says online when eBay shows it", () => {
    expect(listingState(listing())).toMatchObject({ label: "Online", tone: "success" });
  });

  it("moves while a sync is due", () => {
    expect(listingState(listing({ status: "pending", needs_sync: true }))).toMatchObject({
      label: "Wird eingestellt",
      busy: true,
    });
    expect(listingState(listing({ needs_sync: true }))).toMatchObject({ label: "Wird aktualisiert" });
    expect(listingState(listing({ wanted: false, needs_sync: true }))).toMatchObject({ label: "Wird beendet" });
  });

  it("explains what the shop holds back, in German", () => {
    const state = listingState(listing({ status: "failed", error_code: "no_category", external_id: "" }));
    expect(state).toMatchObject({ label: "Wartet", tone: "warning" });
    expect(state.detail).toContain("eBay-Kategorie");
  });

  it("passes on eBay's own refusal", () => {
    const state = listingState(
      listing({ status: "failed", error_code: "25709", error_message: "Invalid value for imageUrls." }),
    );
    expect(state).toMatchObject({
      label: "Von eBay abgelehnt",
      tone: "danger",
      detail: "Invalid value for imageUrls.",
    });
  });

  it("pauses a wanted listing that is sold out", () => {
    expect(listingState(listing({ status: "ended" }))).toMatchObject({ label: "Pausiert" });
    expect(listingState(listing({ status: "ended", wanted: false }))).toMatchObject({ label: "Beendet" });
  });
});

describe("priceWithMarkup", () => {
  it("rounds half up to the cent like the backend", () => {
    expect(priceWithMarkup(4990, 0)).toBe(4990);
    expect(priceWithMarkup(4990, 10)).toBe(5489);
    expect(priceWithMarkup(1999, 15)).toBe(2299);
  });
});

describe("isReady", () => {
  it("needs a mode and no blockers", () => {
    const base: EbayStatusOut = {
      mode: "test",
      status: "connected",
      seller_name: "adp",
      connected_at: null,
      consent_expires_at: null,
      blockers: [],
      fulfillment_policy_id: "F",
      payment_policy_id: "P",
      return_policy_id: "R",
      location_ready: true,
      price_markup_percent: 0,
      made_to_order_quantity: 3,
      orders_checked_until: null,
    };
    expect(isReady({ ...base, blockers: [] })).toBe(true);
    expect(isReady({ ...base, blockers: ["no_location"] })).toBe(false);
    expect(isReady({ ...base, mode: "off" })).toBe(false);
  });
});
