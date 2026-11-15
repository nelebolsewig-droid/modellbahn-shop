import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ToMakeListOut } from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { OrderList } from "./order-list";

const fetchMock = vi.fn<typeof fetch>();
const TO_MAKE = "GET /api/v1/admin/inventory/stock/to-make";

const WAITING: ToMakeListOut = {
  quantity: 3,
  items: [
    {
      variant_id: "v1",
      product_id: "p1",
      model: "Stellwerk Altenau",
      finish: "H0 · Fertigmodell, Rot",
      sku: "MB-000001-H0-FRO",
      quantity: 3,
      oldest_at: "2026-11-12T09:00:00Z",
      orders: [
        { order_id: "o1", number: "MB-2026-00041", placed_at: "2026-11-12T09:00:00Z", quantity: 2 },
        { order_id: "o2", number: "MB-2026-00042", placed_at: "2026-11-14T09:00:00Z", quantity: 1 },
      ],
    },
  ],
};

function desk(toMake: ToMakeListOut = WAITING) {
  routeFetch(fetchMock, {
    "GET /api/v1/admin/orders": () => jsonResponse({ items: [], next_cursor: null }),
    [TO_MAKE]: () => jsonResponse(toMake),
  });
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Zu fertigen", () => {
  it("sits beside Zu versenden with its count and lists what paid orders wait for", async () => {
    desk();
    const user = userEvent.setup();
    renderWithQueryClient(<OrderList staffRole="staff" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("radio", { name: "Zu fertigen (3)" }));

    const row = (await screen.findByRole("link", { name: "Stellwerk Altenau" })).closest("li") as HTMLElement;
    expect(within(row).getByRole("link", { name: "Stellwerk Altenau" })).toHaveAttribute("href", "/admin/modelle/p1");
    expect(row).toHaveTextContent("H0 · Fertigmodell, Rot");
    expect(row).toHaveTextContent("3 Stück");
    expect(within(row).getByRole("link", { name: "MB-2026-00041 (2)" })).toHaveAttribute("href", "/admin/bestellungen/o1");
    expect(within(row).getByRole("link", { name: "MB-2026-00042" })).toBeInTheDocument();
    expect(row).toHaveTextContent("seit 12.11.");
  });

  it("says so when nothing waits", async () => {
    desk({ items: [], quantity: 0 });
    const user = userEvent.setup();
    renderWithQueryClient(<OrderList staffRole="owner" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("radio", { name: "Zu fertigen" }));
    expect(await screen.findByText(/Gerade nichts zu fertigen/)).toBeInTheDocument();
  });

  it("is not there for packers", async () => {
    desk();
    renderWithQueryClient(<OrderList staffRole="packer" onStreamClosed={vi.fn()} />);

    expect(await screen.findByRole("radio", { name: "Zu versenden" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Zu fertigen/ })).toBeNull();
    expect(requestsTo(fetchMock, TO_MAKE)).toHaveLength(0);
  });
});
