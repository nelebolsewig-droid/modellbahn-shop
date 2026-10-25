import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomerAddressOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch, type RouteHandler } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { AddressBook } from "./address-book";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/konto/adressen" }));

const fetchMock = vi.fn<typeof fetch>();

const ACCOUNT = {
  id: "a1",
  email: "erika@example.de",
  display_name: "Erika",
  email_verified: true,
  created_at: "2026-10-01T10:00:00Z",
};

function entry(overrides: Partial<CustomerAddressOut> = {}): CustomerAddressOut {
  return {
    id: "e1",
    label: "",
    recipient: "Erika Mustermann",
    street: "Bahnhofstraße 12",
    postal_code: "38707",
    city: "Altenau",
    country_code: "DE",
    country_name: "Deutschland",
    is_default: true,
    ...overrides,
  };
}

function shop(book: CustomerAddressOut[], routes: Record<string, RouteHandler> = {}) {
  routeFetch(fetchMock, {
    "GET /api/v1/store/account/me": () => jsonResponse(ACCOUNT),
    "GET /api/v1/store/account/addresses": () => jsonResponse(book),
    ...routes,
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("AddressBook", () => {
  it("makes the first address the default without asking", async () => {
    shop([], { "POST /api/v1/store/account/addresses": () => jsonResponse([entry({ label: "Zuhause" })], 201) });
    const user = userEvent.setup();
    renderWithQueryClient(<AddressBook />);

    await user.click(await screen.findByRole("button", { name: /Neue Adresse/ }));
    const form = screen.getByRole("form", { name: "Neue Adresse" });
    expect(within(form).getByText("Die erste Adresse wird deine Standardadresse.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText(/Bezeichnung/), "Zuhause");
    await user.type(within(form).getByLabelText("Name"), "Erika Mustermann");
    await user.type(within(form).getByLabelText("Straße und Hausnummer"), "Bahnhofstraße 12");
    await user.type(within(form).getByLabelText("Postleitzahl"), "38707");
    await user.type(within(form).getByLabelText("Ort"), "Altenau");
    await user.click(within(form).getByRole("button", { name: "Speichern" }));

    expect(await screen.findByText("Zuhause")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "POST /api/v1/store/account/addresses")[0]?.body).toMatchObject({
      label: "Zuhause",
      is_default: true,
      country_code: "DE",
    });
  });

  it("sends a changed address as a whole and shows the book the API answers", async () => {
    const changed = entry({ label: "Werkstatt", street: "Am Lokschuppen 3" });
    shop([entry()], { "PATCH /api/v1/store/account/addresses/e1": () => jsonResponse([changed]) });
    const user = userEvent.setup();
    renderWithQueryClient(<AddressBook />);

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const form = screen.getByRole("form", { name: "Adresse bearbeiten" });
    expect(within(form).getByText("Das ist deine Standardadresse.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText(/Bezeichnung/), "Werkstatt");
    const street = within(form).getByLabelText("Straße und Hausnummer");
    await user.clear(street);
    await user.type(street, "Am Lokschuppen 3");
    await user.click(within(form).getByRole("button", { name: "Speichern" }));

    expect(await screen.findByText("Am Lokschuppen 3", { exact: false })).toBeInTheDocument();
    expect(requestsTo(fetchMock, "PATCH /api/v1/store/account/addresses/e1")[0]?.body).toEqual({
      label: "Werkstatt",
      address: {
        recipient: "Erika Mustermann",
        street: "Am Lokschuppen 3",
        postal_code: "38707",
        city: "Altenau",
        country_code: "DE",
      },
      is_default: true,
    });
  });

  it("asks before removing an address", async () => {
    const second = entry({ id: "e2", is_default: false, recipient: "Verein Altenau", label: "Verein" });
    shop([entry(), second], { "DELETE /api/v1/store/account/addresses/e2": () => jsonResponse([entry()]) });
    const user = userEvent.setup();
    renderWithQueryClient(<AddressBook />);

    const card = (await screen.findByText("Verein")).closest("li");
    await user.click(within(card as HTMLElement).getByRole("button", { name: "Löschen" }));
    const dialog = screen.getByRole("dialog", { name: "Adresse löschen?" });
    await user.click(within(dialog).getByRole("button", { name: "Löschen" }));

    await waitFor(() => expect(screen.queryByText("Verein")).toBeNull());
    expect(screen.getByText("1 von 20")).toBeInTheDocument();
  });
});
