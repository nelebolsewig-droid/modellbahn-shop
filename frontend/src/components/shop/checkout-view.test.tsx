import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";
import { cartLine, cartOut, orderOut } from "@/test/sales";

import { CheckoutView } from "./checkout-view";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const fetchMock = vi.fn<typeof fetch>();
const CHECKOUT = "POST /api/v1/store/checkouts";

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  push.mockReset();
});

function guestShop(checkout: () => Response | Promise<Response>) {
  routeFetch(fetchMock, {
    "GET /api/v1/store/cart": () => jsonResponse(cartOut(cartLine())),
    "GET /api/v1/store/account/me": () => problemResponse(401, "not_authenticated"),
    [CHECKOUT]: checkout,
  });
}

async function fillGuestForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("E-Mail-Adresse"), "erika@example.de");
  await user.type(screen.getByLabelText("Name"), "Erika Mustermann");
  await user.type(screen.getByLabelText("Straße und Hausnummer"), "Bahnhofstraße 12");
  await user.type(screen.getByLabelText("Postleitzahl"), "38707");
  await user.type(screen.getByLabelText("Ort"), "Altenau");
}

describe("CheckoutView", () => {
  it("places a guest order with the total shown and goes on to the payment", async () => {
    guestShop(() => jsonResponse(orderOut(), 201));
    const user = userEvent.setup();
    renderWithQueryClient(<CheckoutView />);

    await fillGuestForm(user);
    await user.click(screen.getByRole("button", { name: "Zahlungspflichtig bestellen" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/bestellung/status-token/bezahlen"));
    const [request] = requestsTo(fetchMock, CHECKOUT);
    expect(request?.body).toEqual({
      expected_total_cents: 7990,
      email: "erika@example.de",
      address: {
        recipient: "Erika Mustermann",
        street: "Bahnhofstraße 12",
        postal_code: "38707",
        city: "Altenau",
        country_code: "DE",
      },
      save_address: false,
    });
    expect(request?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("shows the shipping of the chosen country before ordering", async () => {
    guestShop(() => jsonResponse(orderOut(), 201));
    const user = userEvent.setup();
    renderWithQueryClient(<CheckoutView />);

    await user.selectOptions(await screen.findByLabelText("Land"), "AT");
    expect(screen.getByText("Versand nach Österreich")).toBeInTheDocument();
    expect(screen.getByText("89,80 €")).toBeInTheDocument();
  });

  it("checks the form before anything is sent", async () => {
    guestShop(() => jsonResponse(orderOut(), 201));
    const user = userEvent.setup();
    renderWithQueryClient(<CheckoutView />);

    await user.click(await screen.findByRole("button", { name: "Zahlungspflichtig bestellen" }));
    expect(await screen.findByText("Bitte gib deine E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(screen.getByText("Bitte gib eine fünfstellige Postleitzahl ein.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, CHECKOUT)).toHaveLength(0);
  });

  it("retries a lost request with the same key, so it cannot order twice", async () => {
    let attempts = 0;
    guestShop(() => {
      attempts += 1;
      if (attempts === 1) {
        throw new TypeError("Failed to fetch");
      }
      return jsonResponse(orderOut(), 201);
    });
    const user = userEvent.setup();
    renderWithQueryClient(<CheckoutView />);

    await fillGuestForm(user);
    const order = screen.getByRole("button", { name: "Zahlungspflichtig bestellen" });
    await user.click(order);
    expect(await screen.findByText(/Keine Verbindung zum Server/)).toBeInTheDocument();
    await user.click(order);

    await waitFor(() => expect(push).toHaveBeenCalled());
    const [first, second] = requestsTo(fetchMock, CHECKOUT);
    expect(second?.headers.get("Idempotency-Key")).toBe(first?.headers.get("Idempotency-Key"));
  });

  it("reloads the cart when the prices changed meanwhile", async () => {
    guestShop(() => problemResponse(409, "price_changed"));
    const user = userEvent.setup();
    renderWithQueryClient(<CheckoutView />);

    await fillGuestForm(user);
    await user.click(screen.getByRole("button", { name: "Zahlungspflichtig bestellen" }));

    expect(await screen.findByText(/Die Preise haben sich gerade geändert/)).toBeInTheDocument();
    await waitFor(() => expect(requestsTo(fetchMock, "GET /api/v1/store/cart")).toHaveLength(2));
    expect(push).not.toHaveBeenCalled();
  });
});
