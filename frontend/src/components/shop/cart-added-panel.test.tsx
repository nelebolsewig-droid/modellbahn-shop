import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { announceCartAdded, dismissCartAdded } from "@/lib/sales/cart-added";

import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";
import { cartLine, cartOut } from "@/test/sales";

import { CartAddedPanel } from "./cart-added-panel";

vi.mock("next/navigation", () => ({
  usePathname: () => "/produkte/stellwerk-altenau",
}));

const fetchMock = vi.fn<typeof fetch>();

describe("CartAddedPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    routeFetch(fetchMock, {
      "GET /api/v1/store/cart": () => jsonResponse(cartOut(cartLine({ variant_id: "v1", quantity: 2 }))),
    });
  });
  afterEach(() => act(dismissCartAdded));

  it("stays closed until something was added", () => {
    renderWithQueryClient(<CartAddedPanel />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows what went in and leads to the checkout", async () => {
    renderWithQueryClient(<CartAddedPanel />);
    act(() =>
      announceCartAdded({
        variantId: "v1",
        title: "Stellwerk Altenau · H0 · Bausatz",
        quantity: 1,
      }),
    );
    const panel = await screen.findByRole("dialog", { name: "Im Warenkorb" });
    expect(panel).toHaveTextContent("Stellwerk Altenau · H0 · Bausatz");
    await waitFor(() => expect(panel).toHaveTextContent("2 im Warenkorb"));
    const checkout = screen.getByRole("link", { name: "Zur Kasse" });
    expect(checkout).toHaveAttribute("href", "/kasse");
    expect(checkout).toHaveFocus();
  });

  it("closes with „Weiter stöbern“", async () => {
    renderWithQueryClient(<CartAddedPanel />);
    act(() =>
      announceCartAdded({
        variantId: "v1",
        title: "Stellwerk Altenau",
        quantity: 1,
      }),
    );
    (await screen.findByRole("button", { name: "Weiter stöbern" })).click();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
