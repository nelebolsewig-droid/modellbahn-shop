import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OrderStatus, OrderSummaryOut } from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { OrderTrack } from "./order-track";

const fetchMock = vi.fn<typeof fetch>();

function order(id: string, status: OrderStatus, overrides: Partial<OrderSummaryOut> = {}): OrderSummaryOut {
  return {
    id,
    number: `2026-${id}`,
    status,
    placed_at: "2026-11-17T08:00:00Z",
    first_line_title: `Modell ${id}`,
    recipient: "Jana Beispiel",
    channel: "shop",
    guest: false,
    item_count: 1,
    total_cents: 4990,
    ...overrides,
  };
}

const ORDERS = [
  order("0415", "paid"),
  order("0414", "pending_payment"),
  order("0412", "paid"),
  order("0409", "paid", { channel: "ebay" }),
  order("0400", "shipped"),
  // Withdrawn and refunded: its label was cancelled, it is not on its way.
  order("0398", "shipped", { refunded: true }),
];

const TO_MAKE = {
  quantity: 1,
  items: [
    {
      variant_id: "v1",
      sku: "MB-1",
      model: "Modell 0412",
      finish: "H0 · Bausatz",
      quantity: 1,
      product_id: "p1",
      oldest_at: "2026-11-15T08:00:00Z",
      orders: [{ order_id: "0412", number: "2026-0412", placed_at: "2026-11-15T08:00:00Z", quantity: 1 }],
    },
  ],
};

/** The orders answer by the asked state, which the shared route table cannot see. */
function routes() {
  fetchMock.mockImplementation(async (input) => {
    const url = new URL(String(input), "http://shop.test");
    if (url.pathname === "/api/v1/admin/orders") {
      const states = url.searchParams.getAll("status");
      return jsonResponse({ items: ORDERS.filter((entry) => states.includes(entry.status)), next_cursor: null });
    }
    if (url.pathname === "/api/v1/admin/inventory/stock/to-make") {
      return jsonResponse(TO_MAKE);
    }
    throw new Error(`unexpected request: ${url.pathname}`);
  });
}

const wagons = (station: string) =>
  within(screen.getByRole("list", { name: `${station}, älteste zuerst` }))
    .getAllByRole("link")
    .map((link) => link.getAttribute("href"));

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Gleisbild", () => {
  it("puts every order at the station of its state; paid ones that wait for a piece stand in the Fertigung", async () => {
    routes();
    renderWithQueryClient(<OrderTrack staffRole="owner" onStreamClosed={vi.fn()} onOpenList={vi.fn()} />);

    await screen.findByRole("heading", { name: /Versand/ });
    expect(wagons("Eingang")).toEqual(["/admin/bestellungen/0414"]);
    expect(wagons("Fertigung")).toEqual(["/admin/bestellungen/0412"]);
    // The oldest wagon leads; orders arrive newest first.
    expect(wagons("Versand")).toEqual(["/admin/bestellungen/0409", "/admin/bestellungen/0415"]);
    expect(wagons("Unterwegs")).toEqual(["/admin/bestellungen/0400"]);
    expect(screen.getByRole("button", { name: "Versand: 2" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a packer no Fertigung and asks nothing about making", async () => {
    routes();
    renderWithQueryClient(<OrderTrack staffRole="packer" onStreamClosed={vi.fn()} onOpenList={vi.fn()} />);

    await screen.findByRole("heading", { name: /Versand/ });
    expect(screen.queryByRole("heading", { name: /Fertigung/ })).toBeNull();
    expect(wagons("Versand")).toHaveLength(3);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/stock/to-make"))).toBe(false);
  });

  it("opens the list on a station's state", async () => {
    routes();
    const onOpenList = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<OrderTrack staffRole="owner" onStreamClosed={vi.fn()} onOpenList={onOpenList} />);

    await user.click(await screen.findByRole("button", { name: "Alle versendeten" }));
    expect(onOpenList).toHaveBeenCalledWith("shipped");
  });
});
