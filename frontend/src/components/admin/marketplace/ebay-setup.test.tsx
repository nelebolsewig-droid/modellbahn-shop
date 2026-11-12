import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EbayStatusOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { EbaySetupDesk } from "./ebay-setup";

const fetchMock = vi.fn<typeof fetch>();
const OPT_IN = "POST /api/v1/admin/marketplace/ebay/policies/opt-in";

const CONNECTED: EbayStatusOut = {
  blockers: [],
  connected_at: "2026-11-10T10:00:00Z",
  consent_expires_at: "2028-05-10T10:00:00Z",
  fulfillment_policy_id: "",
  location_ready: true,
  made_to_order_quantity: 3,
  mode: "production",
  orders_checked_until: null,
  payment_policy_id: "",
  price_markup_percent: 0,
  return_policy_id: "",
  seller_name: "adp-modelle",
  status: "connected",
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("eBay setup without business policies", () => {
  it("says what is missing and turns the policies on for the owner", async () => {
    routeFetch(fetchMock, {
      "GET /api/v1/admin/auth/me": () =>
        jsonResponse({ id: "s1", email: "johann@example.de", display_name: "Johann", role: "owner" }),
      "GET /api/v1/admin/marketplace/ebay": () => jsonResponse(CONNECTED),
      "GET /api/v1/admin/marketplace/ebay/policies": () => problemResponse(409, "ebay_policies_not_enabled"),
      "GET /api/v1/admin/marketplace/ebay/categories": () => jsonResponse({ items: [] }),
      [OPT_IN]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<EbaySetupDesk outcome={null} />);

    expect(await screen.findByText("Euer eBay-Konto nutzt noch keine Grundsätze für Angebote.")).toBeInTheDocument();
    expect(screen.queryByText("eBay hat die Anfrage abgelehnt.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Grundsätze bei eBay einschalten" }));

    expect(await screen.findByText(/Eingeschaltet\. Jetzt die drei Grundsätze auf eBay anlegen\./)).toBeInTheDocument();
    expect(requestsTo(fetchMock, OPT_IN)).toHaveLength(1);
  });
});
