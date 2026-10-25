import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminOrderOut } from "@/lib/api/generated/model";
import { FakeEventSource, latestSource } from "@/test/event-source";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";
import { orderOut } from "@/test/sales";

import { OrderDesk } from "./order-desk";

const fetchMock = vi.fn<typeof fetch>();
const ORDER = "GET /api/v1/admin/orders/o1";

function adminOrder(overrides: Partial<AdminOrderOut> = {}): AdminOrderOut {
  return {
    ...orderOut({ status: "paid", paid_at: "2026-10-25T09:02:00Z", payment_due_at: null }),
    id: "o1",
    customer_account_id: null,
    cancel_note: "",
    ...overrides,
  };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("OrderDesk", () => {
  it("lets a packer ship a paid order, but not cancel it", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      "POST /api/v1/admin/orders/o1/ship": () =>
        jsonResponse(adminOrder({ status: "shipped", shipped_at: "2026-10-25T14:00:00Z", carrier: "DHL", tracking_number: "00340434" })),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />);

    const shipping = await screen.findByRole("form", { name: "Versand melden" });
    expect(screen.queryByRole("button", { name: /stornieren/ })).toBeNull();
    await user.type(within(shipping).getByLabelText("Sendungsnummer"), " 00340434 ");
    await user.click(within(shipping).getByRole("button", { name: "Als versendet melden" }));

    expect(await screen.findByText("00340434")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "POST /api/v1/admin/orders/o1/ship")[0]?.body).toEqual({
      carrier: "DHL",
      tracking_number: "00340434",
    });
  });

  it("cancels after confirming and says that the payment goes back", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      "POST /api/v1/admin/orders/o1/cancel": () =>
        jsonResponse(
          adminOrder({ status: "cancelled", cancelled_at: "2026-10-25T10:00:00Z", cancel_reason: "by_shop", cancel_note: "Nicht lieferbar" }),
        ),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<OrderDesk orderId="o1" staffRole="staff" onStreamClosed={vi.fn()} />);

    expect(await screen.findByText(/Die Zahlung über 79,90 € wird dabei erstattet/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bestellung stornieren …" }));
    const dialog = screen.getByRole("dialog", { name: "MB-2026-00042 stornieren?" });
    await user.type(within(dialog).getByLabelText("Hinweis an den Kunden"), "Nicht lieferbar");
    await user.click(within(dialog).getByRole("button", { name: "Stornieren" }));

    expect(await screen.findByText("„Nicht lieferbar“")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Storniert – nicht verschicken.")).toBeInTheDocument();
  });

  it("reloads when an event about this order arrives", async () => {
    routeFetch(fetchMock, { [ORDER]: () => jsonResponse(adminOrder()) });
    renderWithQueryClient(<OrderDesk orderId="o1" staffRole="owner" onStreamClosed={vi.fn()} />);
    await screen.findByRole("form", { name: "Versand melden" });

    const event = (orderId: string) => ({
      id: `e-${orderId}`,
      type: "sales.order.shipped",
      occurred_at: "2026-10-25T14:00:00Z",
      data: { order_id: orderId, number: "MB-2026-00042", total_cents: 7990 },
      truncated: false,
    });
    act(() => latestSource().emit("sales.order.shipped", event("someone-else")));
    act(() => latestSource().emit("sales.order.shipped", event("o1")));

    await waitFor(() => expect(requestsTo(fetchMock, ORDER)).toHaveLength(2));
  });
});
