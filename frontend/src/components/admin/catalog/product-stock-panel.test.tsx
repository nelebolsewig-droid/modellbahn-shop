import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPanel } from "@/components/admin/inventory/stock-panel";
import type { ProductOut, ReferencesOut, StockLineOut, VariantOut } from "@/lib/api/generated/model";
import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { ProductStockPanel } from "./product-stock-panel";

const fetchMock = vi.fn<typeof fetch>();

const REFERENCES: ReferencesOut = {
  scales: [{ code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 }],
  finishes: [
    { code: "unpainted", name: "Bausatz", sku_letter: "B", colored: false, offered: true },
    { code: "painted", name: "Fertigmodell", sku_letter: "F", colored: true, offered: true },
  ],
  epochs: [],
};

function variant(id: string, finish: string, color: string, sku: string): VariantOut {
  return {
    id,
    finish_code: finish,
    color,
    sku,
    gtin: "2000000000015",
    price_cents: 4990,
    compare_at_price_cents: null,
    active: true,
    allow_backorder: false,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
  };
}

const PRODUCT: ProductOut = {
  id: "p1",
  number: 1,
  name: "Stellwerk Altenau",
  slug: "stellwerk-altenau",
  status: "active",
  summary: "",
  description: "",
  prototype: "",
  primary_category_id: null,
  epoch_codes: [],
  scales: [
    {
      id: "s1",
      scale_code: "H0",
      length_mm: null,
      width_mm: null,
      height_mm: null,
      weight_g: null,
      variants: [variant("v1", "unpainted", "", "MB-000001-H0-B"), variant("v2", "painted", "Rot", "MB-000001-H0-F")],
    },
  ],
  media: [],
  publish_blockers: [],
  published_at: null,
  archived_at: null,
  created_at: "2026-10-28T10:00:00Z",
  updated_at: "2026-10-28T10:00:00Z",
  version: 3,
};

const LINE: StockLineOut = {
  variant_id: "v1",
  variant: {
    variant_id: "v1",
    product_id: "p1",
    product_slug: "stellwerk-altenau",
    title: "Stellwerk Altenau · H0 · Bausatz",
    sku: "MB-000001-H0-B",
    gtin: "2000000000015",
    allow_backorder: false,
  },
  labeled: 2,
  in_stock: 3,
  allocated: 1,
  picked: 1,
  backordered: 1,
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  routeFetch(fetchMock, {
    "GET /api/v1/admin/inventory/stock": () => jsonResponse({ items: [LINE] }),
    "GET /api/v1/admin/inventory/locations": () => jsonResponse({ items: [] }),
  });
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ProductStockPanel", () => {
  it("shows free, reserved and unbooked pieces per Ausführung with the way to them", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ProductStockPanel product={PRODUCT} references={REFERENCES} />);

    const items = await screen.findAllByRole("listitem");
    const kit = items[0] as HTMLElement;
    const painted = items[1] as HTMLElement;
    expect(kit).toHaveTextContent("H0 · Bausatz");
    expect(kit).toHaveTextContent("Frei3Reserviert2Unverbucht2");
    expect(kit).toHaveTextContent("1 bestelltes Stück wartet auf die Fertigung.");
    expect(within(kit).getByRole("link", { name: /^Stücke.*H0 · Bausatz$/ })).toHaveAttribute("href", "/admin/lager/einheiten?artikel=v1");
    // Without a line in the store an Ausführung has nothing yet.
    expect(painted).toHaveTextContent("H0 · Fertigmodell, Rot");
    expect(painted).toHaveTextContent("Frei0Reserviert0Unverbucht0");

    await user.click(within(painted).getByRole("button", { name: "Stücke erfassen: H0 · Fertigmodell, Rot" }));
    const dialog = await screen.findByRole("dialog", { name: "Stücke erfassen" });
    expect(dialog).toHaveTextContent("Stellwerk Altenau · H0 · Fertigmodell, Rot");
    expect(dialog).toHaveTextContent("MB-000001-H0-F");
  });
});

describe("StockPanel", () => {
  it("links every article to its Modell in the Katalog, for owner and staff", async () => {
    const { unmount } = renderWithQueryClient(<StockPanel mayManage />);
    expect(await screen.findByRole("link", { name: /^Modell.*Stellwerk Altenau · H0 · Bausatz im Katalog$/ })).toHaveAttribute(
      "href",
      "/admin/katalog/p1",
    );
    unmount();

    renderWithQueryClient(<StockPanel mayManage={false} />);
    expect(await screen.findByRole("link", { name: /^Stücke/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /im Katalog/ })).not.toBeInTheDocument();
  });
});
