import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AdminOrderOut,
  PickListOut,
  ShippingLabelOut,
} from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import {
  jsonResponse,
  problemResponse,
  renderWithQueryClient,
} from "@/test/render";
import { orderOut } from "@/test/sales";

import { OrderDesk } from "./order-desk";
import { groupDigits, parseWeight } from "./shipping-label";

const fetchMock = vi.fn<typeof fetch>();
const ORDER = "GET /api/v1/admin/orders/o1";
const PICK_LIST = "GET /api/v1/admin/inventory/orders/o1/pick-list";
const SETUP = "GET /api/v1/admin/shipping/setup";
const LABEL = "GET /api/v1/admin/orders/o1/shipping-label";
const BOOK = "POST /api/v1/admin/orders/o1/shipping-label";
const CANCEL = "DELETE /api/v1/admin/orders/o1/shipping-label";

function adminOrder(overrides: Partial<AdminOrderOut> = {}): AdminOrderOut {
  return {
    ...orderOut({
      status: "paid",
      paid_at: "2026-10-25T09:02:00Z",
      payment_due_at: null,
    }),
    id: "o1",
    customer_account_id: null,
    cancel_note: "",
    channel: "shop",
    external_ref: null,
    ...overrides,
  };
}

const PACKED: PickListOut = {
  order_id: "o1",
  order_number: "MB-2026-00042",
  order_status: "paid",
  ship_recipient: "Erika Mustermann",
  allocated: true,
  items: [],
  picked: 1,
  total: 1,
  complete: true,
};

const BOOKED: ShippingLabelOut = {
  carrier: "DHL",
  product: "V01PAK",
  shipment_number: "00340434161094042557",
  weight_g: 850,
  print_format: "910-300-400",
  created_at: "2026-10-25T13:40:00Z",
};

const DHL_SETUP = {
  books_labels: true,
  carrier: "DHL",
  default_weight_g: 1000,
};

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("shipping label at the order desk", () => {
  it("books the label with the weight and puts its number into the dispatch", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      [PICK_LIST]: () => jsonResponse(PACKED),
      [SETUP]: () => jsonResponse(DHL_SETUP),
      [LABEL]: () => problemResponse(404, "label_not_found"),
      [BOOK]: () => jsonResponse(BOOKED, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    const booking = await screen.findByRole("form", {
      name: "DHL-Label buchen",
    });
    expect(within(booking).getByText("DHL Paket")).toBeInTheDocument();
    const weight = within(booking).getByLabelText("Gewicht in Gramm");
    expect(weight).toHaveValue("1000");
    await user.clear(weight);
    await user.type(weight, "850");
    await user.click(
      within(booking).getByRole("button", { name: "DHL-Label buchen" }),
    );

    expect(
      await screen.findByText("0034 0434 1610 9404 2557"),
    ).toBeInTheDocument();
    expect(requestsTo(fetchMock, BOOK)[0]?.body).toEqual({ weight_g: 850 });
    expect(screen.getByRole("link", { name: "Label drucken" })).toHaveAttribute(
      "href",
      "/api/v1/admin/orders/o1/shipping-label.pdf",
    );
    const dispatch = screen.getByRole("form", { name: "Versand melden" });
    expect(within(dispatch).getByLabelText("Sendungsnummer")).toHaveValue(
      "00340434161094042557",
    );
    expect(within(dispatch).getByLabelText("Versanddienst")).toHaveValue("DHL");
  });

  it("refuses a weight DHL does not carry before asking DHL", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      [PICK_LIST]: () => jsonResponse(PACKED),
      [SETUP]: () => jsonResponse(DHL_SETUP),
      [LABEL]: () => problemResponse(404, "label_not_found"),
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    const booking = await screen.findByRole("form", {
      name: "DHL-Label buchen",
    });
    const weight = within(booking).getByLabelText("Gewicht in Gramm");
    await user.clear(weight);
    await user.type(weight, "40000");
    await user.click(
      within(booking).getByRole("button", { name: "DHL-Label buchen" }),
    );

    expect(await within(booking).findByText(/31,5 kg/)).toBeInTheDocument();
    expect(requestsTo(fetchMock, BOOK)).toHaveLength(0);
  });

  it("shows DHL's own words when it refuses the label", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      [PICK_LIST]: () => jsonResponse(PACKED),
      [SETUP]: () => jsonResponse(DHL_SETUP),
      [LABEL]: () => problemResponse(404, "label_not_found"),
      [BOOK]: () =>
        jsonResponse(
          {
            type: "/problems/carrier-rejected",
            title: "Conflict",
            status: 409,
            detail: "consignee.postalCode: Die Postleitzahl ist ungültig.",
            code: "carrier_rejected",
          },
          409,
          "application/problem+json",
        ),
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    const booking = await screen.findByRole("form", {
      name: "DHL-Label buchen",
    });
    await user.click(
      within(booking).getByRole("button", { name: "DHL-Label buchen" }),
    );

    expect(
      await within(booking).findByText(/DHL hat das abgelehnt/),
    ).toBeInTheDocument();
    expect(
      within(booking).getByText(
        "consignee.postalCode: Die Postleitzahl ist ungültig.",
      ),
    ).toBeInTheDocument();
  });

  it("cancels a wrong label after asking, then offers to book anew", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      [PICK_LIST]: () => jsonResponse(PACKED),
      [SETUP]: () => jsonResponse(DHL_SETUP),
      [LABEL]: () => jsonResponse(BOOKED),
      [CANCEL]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    await user.click(
      await screen.findByRole("button", { name: "Label stornieren" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "DHL-Label stornieren?",
    });
    expect(
      within(dialog).getByText("0034 0434 1610 9404 2557"),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Label stornieren" }),
    );

    expect(
      await screen.findByRole("form", { name: "DHL-Label buchen" }),
    ).toBeInTheDocument();
    expect(requestsTo(fetchMock, CANCEL)).toHaveLength(1);
    expect(
      within(
        screen.getByRole("form", { name: "Versand melden" }),
      ).getByLabelText("Sendungsnummer"),
    ).toHaveValue("");
  });

  it("keeps typing the number by hand when no carrier is connected", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(adminOrder()),
      [PICK_LIST]: () => jsonResponse(PACKED),
      [SETUP]: () => jsonResponse({ ...DHL_SETUP, books_labels: false }),
    });
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    expect(
      await screen.findByRole("form", { name: "Versand melden" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "DHL-Label buchen" })).toBeNull();
    expect(requestsTo(fetchMock, LABEL)).toHaveLength(0);
  });

  it("offers the label of a shipped order for printing again, but no cancelling", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () =>
        jsonResponse(
          adminOrder({
            status: "shipped",
            shipped_at: "2026-10-25T14:00:00Z",
            carrier: "DHL",
            tracking_number: BOOKED.shipment_number,
          }),
        ),
      [PICK_LIST]: () => jsonResponse({ ...PACKED, order_status: "shipped" }),
      [SETUP]: () => jsonResponse(DHL_SETUP),
      [LABEL]: () => jsonResponse(BOOKED),
    });
    renderWithQueryClient(
      <OrderDesk orderId="o1" staffRole="packer" onStreamClosed={vi.fn()} />,
    );

    expect(
      await screen.findByRole("link", { name: "DHL-Label öffnen" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Label stornieren" }),
    ).toBeNull();
  });
});

describe("parseWeight", () => {
  it.each([
    ["850", 850],
    [" 1.250 ", 1250],
    ["10", 10],
    ["31500", 31500],
  ])("reads %j as %d g", (text, grams) => {
    expect(parseWeight(text)).toEqual({ grams });
  });

  it.each(["", "1,5", "9", "31501", "abc"])("refuses %j", (text) => {
    expect(parseWeight(text)).toHaveProperty("problem");
  });
});

describe("groupDigits", () => {
  it("groups by four", () => {
    expect(groupDigits("00340434161094042557")).toBe(
      "0034 0434 1610 9404 2557",
    );
    expect(groupDigits("123456")).toBe("1234 56");
  });
});
