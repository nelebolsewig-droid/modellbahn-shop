import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProductListItemOut, ProductStockOut } from "@/lib/api/generated/model";
import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { ProductList, withoutStock } from "./product-list";

const fetchMock = vi.fn<typeof fetch>();

function item(id: string, name: string, overrides: Partial<ProductListItemOut> = {}): ProductListItemOut {
  return {
    id,
    name,
    number: Number(id.slice(1)),
    slug: name.toLowerCase(),
    status: "active",
    main_image: null,
    price_from_cents: 4990,
    published_at: null,
    scale_codes: ["H0"],
    updated_at: "2026-11-15T10:00:00Z",
    variant_count: 1,
    ...overrides,
  };
}

const STOCK: ProductStockOut = {
  product_id: "p1",
  free: 7,
  reserved: 1,
  labeled: 0,
  backordered: 0,
  places: [{ code: "R02-B03", place: "Regal 2, Boden 3", quantity: 8 }],
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Modelle", () => {
  it("shows each model with status, eBay, free and reserved pieces and their places", async () => {
    routeFetch(fetchMock, {
      "GET /api/v1/admin/products": () =>
        jsonResponse({ items: [item("p1", "Stellwerk Altenau"), item("p2", "Lokschuppen", { status: "draft" })], next_cursor: null }),
      "GET /api/v1/admin/inventory/stock/products": () => jsonResponse({ items: [STOCK] }),
      "GET /api/v1/admin/marketplace/ebay/listings": () =>
        jsonResponse({ items: [{ product_id: "p1", status: "active" }], next_cursor: null }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ProductList />);

    const stellwerk = (await screen.findByText("Stellwerk Altenau")).closest("a") as HTMLElement;
    expect(stellwerk).toHaveAttribute("href", "/admin/modelle/p1");
    expect(within(stellwerk).getByText("Im Shop")).toBeInTheDocument();
    expect(await within(stellwerk).findByText("eBay")).toBeInTheDocument();
    expect(within(stellwerk).getByText("8 · Regal 2, Boden 3")).toBeInTheDocument();
    expect(stellwerk).toHaveTextContent("7 frei · 1 reserviert");
    const schuppen = screen.getByText("Lokschuppen").closest("a") as HTMLElement;
    expect(within(schuppen).getByText("Entwurf")).toBeInTheDocument();
    expect(within(schuppen).queryByText("eBay")).toBeNull();

    await user.click(screen.getByRole("radio", { name: "Ohne Bestand" }));
    expect(screen.queryByText("Stellwerk Altenau")).toBeNull();
    expect(screen.getByText("Lokschuppen")).toBeInTheDocument();
  });

  it("knows eBay offers beyond the first page of listings", async () => {
    let pages = 0;
    routeFetch(fetchMock, {
      "GET /api/v1/admin/products": () =>
        jsonResponse({ items: [item("p1", "Stellwerk Altenau"), item("p2", "Lokschuppen")], next_cursor: null }),
      "GET /api/v1/admin/inventory/stock/products": () => jsonResponse({ items: [] }),
      "GET /api/v1/admin/marketplace/ebay/listings": () => {
        pages += 1;
        return pages === 1
          ? jsonResponse({ items: [{ product_id: "p1", status: "ended" }], next_cursor: "seite-2" })
          : jsonResponse({ items: [{ product_id: "p2", status: "active" }], next_cursor: null });
      },
    });
    renderWithQueryClient(<ProductList />);

    const schuppen = (await screen.findByText("Lokschuppen")).closest("a") as HTMLElement;
    expect(await within(schuppen).findByText("eBay")).toBeInTheDocument();
    const stellwerk = screen.getByText("Stellwerk Altenau").closest("a") as HTMLElement;
    expect(within(stellwerk).queryByText("eBay")).toBeNull();
    const asked = fetchMock.mock.calls
      .map(([input]) => new URL(String(input), "http://shop.test"))
      .filter((url) => url.pathname.endsWith("/ebay/listings"))
      .map((url) => url.searchParams.get("cursor"));
    expect(asked).toEqual([null, "seite-2"]);
  });

  it("works without eBay", async () => {
    routeFetch(fetchMock, {
      "GET /api/v1/admin/products": () => jsonResponse({ items: [item("p1", "Stellwerk Altenau")], next_cursor: null }),
      "GET /api/v1/admin/inventory/stock/products": () => jsonResponse({ items: [] }),
      "GET /api/v1/admin/marketplace/ebay/listings": () => problemResponse(409, "marketplace_not_connected"),
    });
    renderWithQueryClient(<ProductList />);
    const row = (await screen.findByText("Stellwerk Altenau")).closest("a") as HTMLElement;
    expect(row).toHaveTextContent("0 frei");
  });

  it("counts a model without free or reserved pieces as without stock", () => {
    const stock = new Map([["p1", STOCK], ["p2", { ...STOCK, product_id: "p2", free: 0, reserved: 0 }]]);
    expect([withoutStock(item("p1", "A"), stock), withoutStock(item("p2", "B"), stock), withoutStock(item("p3", "C"), stock)]).toEqual([
      false,
      true,
      true,
    ]);
  });
});
