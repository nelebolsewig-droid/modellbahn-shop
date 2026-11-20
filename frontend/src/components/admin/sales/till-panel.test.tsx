import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TillOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { TillPanel } from "./till-panel";

const fetchMock = vi.fn<typeof fetch>();
const TILL = "GET /api/v1/admin/inventory/till";
const DONE = "POST /api/v1/admin/inventory/till/lines/l2/done";
const ASSIGN = "PUT /api/v1/admin/inventory/till/items";

const WAITING: TillOut = {
  enabled: true,
  since: "2026-11-20T14:00:00Z",
  last_sync_at: "2026-11-20T15:02:00Z",
  last_error: "",
  booked_today: 3,
  open: [
    {
      id: "l1",
      transaction_code: "TAAA6QETUD6",
      sold_at: "2026-10-03T08:12:17Z",
      payment: "cash",
      name: "K700 tt",
      quantity: 1,
      booked: 0,
      unit_price_cents: 3000,
      state: "unassigned",
      variant: null,
    },
    {
      id: "l2",
      transaction_code: "TAAA6QQPV9F",
      sold_at: "2026-10-03T14:16:30Z",
      payment: "card",
      name: "Individueller Betrag",
      quantity: 1,
      booked: 0,
      unit_price_cents: 6000,
      state: "custom",
      variant: null,
    },
  ],
  items: [],
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Kasse", () => {
  it("shows what the till could not book and lets it be marked done", async () => {
    routeFetch(fetchMock, {
      [TILL]: () => jsonResponse(WAITING),
      [DONE]: () => jsonResponse({ ...WAITING, open: WAITING.open.slice(0, 1) }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<TillPanel />);

    expect(await screen.findByText("Heute hat die Kasse 3 Stück selbst ausgebucht.")).toBeInTheDocument();
    expect(screen.getByText("2 Kassenverkäufe brauchen einen Blick")).toBeInTheDocument();
    const custom = screen.getByText("Individueller Betrag").closest("li") as HTMLElement;
    expect(within(custom).getByText("Preis ohne Artikel: bitte von Hand ausbuchen")).toBeInTheDocument();

    await user.click(within(custom).getByRole("button", { name: "Erledigt, von Hand ausgebucht" }));
    expect(requestsTo(fetchMock, DONE)).toHaveLength(1);
    expect(await screen.findByText("1 Kassenverkauf braucht einen Blick")).toBeInTheDocument();
  });

  it("marks a name as no model from the assign dialog", async () => {
    routeFetch(fetchMock, {
      [TILL]: () => jsonResponse(WAITING),
      [ASSIGN]: () => jsonResponse({ ...WAITING, open: WAITING.open.slice(1) }),
      "GET /api/v1/admin/catalog/products": () => jsonResponse({ items: [], next_cursor: null, total: 0 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<TillPanel />);

    const unassigned = (await screen.findByText("K700 tt")).closest("li") as HTMLElement;
    await user.click(within(unassigned).getByRole("button", { name: "Modell zuordnen" }));
    await user.click(await screen.findByRole("button", { name: "Kein Modell (z. B. Porto)" }));

    expect(requestsTo(fetchMock, ASSIGN)[0]?.body).toEqual({ name: "K700 tt", variant_id: null, ignored: true });
    expect(await screen.findByText("1 Kassenverkauf braucht einen Blick")).toBeInTheDocument();
  });

  it("says when SumUp cannot be reached", async () => {
    routeFetch(fetchMock, { [TILL]: () => jsonResponse({ ...WAITING, last_error: "SumUp ist nicht erreichbar." }) });
    renderWithQueryClient(<TillPanel />);
    expect(await screen.findByText("SumUp nicht erreichbar")).toBeInTheDocument();
  });

  it("stays away while the till is not connected", async () => {
    routeFetch(fetchMock, { [TILL]: () => jsonResponse({ ...WAITING, enabled: false, open: [], items: [] }) });
    const { container } = renderWithQueryClient(<TillPanel />);
    await vi.waitFor(() => expect(requestsTo(fetchMock, TILL)).toHaveLength(1));
    expect(container).toBeEmptyDOMElement();
  });
});
