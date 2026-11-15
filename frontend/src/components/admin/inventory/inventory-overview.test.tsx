import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationNodeOut, PlaceStockOut, StockLineOut } from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch, type RouteHandler } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { InventoryOverview, racks } from "./inventory-overview";

const fetchMock = vi.fn<typeof fetch>();
const INVENTORY = "/api/v1/admin/inventory";

function node(code: string, kind: LocationNodeOut["kind"], name: string, parent: string | null, holds = kind !== "site"): LocationNodeOut {
  return {
    id: code,
    code,
    path: code,
    kind,
    name,
    parent_id: parent,
    holds_goods: holds,
    depth: 0,
    unit_count: 0,
    total_count: 0,
    part_count: 0,
    place: kind === "compartment" ? `Regal 1, ${name}` : name || code,
  };
}

const TREE = [
  node("LAGER", "site", "Lager", null),
  node("R01", "shelf", "Regal 1", "LAGER", false),
  node("R01-B01", "compartment", "Boden 1", "R01"),
  node("R01-B02", "compartment", "Boden 2", "R01"),
  node("R02", "shelf", "Regal 2", "LAGER"),
  node("PACK", "staging", "Packtisch", "LAGER"),
];

const LINE: PlaceStockOut = {
  location: TREE[2] as LocationNodeOut,
  place: "Regal 1, Boden 1",
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
  free: 6,
  reserved: 1,
};

function stockLine(labeled: number): StockLineOut {
  return { variant_id: "v1", variant: null, labeled, in_stock: 6, allocated: 1, picked: 0, backordered: 0 };
}

function store(routes: Record<string, RouteHandler> = {}) {
  routeFetch(fetchMock, {
    [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
    [`GET ${INVENTORY}/stock/places`]: () => jsonResponse({ items: [LINE] }),
    [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: [stockLine(0)] }),
    [`GET ${INVENTORY}/receiving`]: () => jsonResponse({ items: [] }),
    [`GET ${INVENTORY}/parts`]: () => jsonResponse({ items: [] }),
    ...routes,
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

describe("Lager", () => {
  it("groups places by shelf: Böden, a shelf without Böden, and the rest", () => {
    expect(racks(TREE).map((rack) => [rack.shelf?.code ?? null, rack.places.map((place) => place.code)])).toEqual([
      ["R01", ["R01-B01", "R01-B02"]],
      ["R02", ["R02"]],
      [null, ["PACK"]],
    ]);
  });

  it("shows shelves and Böden with the models on them, linked to the model", async () => {
    store();
    renderWithQueryClient(<InventoryOverview staffRole="packer" onStreamClosed={vi.fn()} />);

    const shelf = await screen.findByRole("region", { name: "Regal 1" });
    const model = within(shelf).getByRole("link", { name: "Stellwerk Altenau · H0 · Bausatz" });
    expect(model).toHaveAttribute("href", "/admin/modelle/p1");
    expect(model.closest("li")).toHaveTextContent("7 (1 reserviert)");
    expect(screen.getByRole("region", { name: "Weitere Plätze" })).toHaveTextContent("Packtisch");
    // Packers look; they make no shelves and count nothing.
    expect(screen.queryByRole("button", { name: "Neues Regal" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Zählen" })).toBeNull();
  });

  it("makes a shelf with its Böden in one step and offers all their labels", async () => {
    store({
      [`POST ${INVENTORY}/locations/shelves`]: () =>
        jsonResponse(
          {
            shelf: { ...node("R03", "shelf", "Regal am Fenster", "LAGER", false) },
            levels: [node("R03-B01", "compartment", "Boden 1", "R03"), node("R03-B02", "compartment", "Boden 2", "R03")],
          },
          201,
        ),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<InventoryOverview staffRole="owner" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Neues Regal" }));
    const dialog = await screen.findByRole("dialog", { name: "Neues Regal" });
    await user.type(within(dialog).getByLabelText("Name"), "Regal am Fenster");
    await user.clear(within(dialog).getByLabelText("Böden"));
    await user.type(within(dialog).getByLabelText("Böden"), "2");
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    const done = await screen.findByRole("dialog", { name: "Regal am Fenster ist angelegt" });
    expect(requestsTo(fetchMock, `POST ${INVENTORY}/locations/shelves`)[0]?.body).toEqual({ name: "Regal am Fenster", levels: 2 });
    expect(within(done).getByText((_, element) => element?.tagName === "P" && element.textContent === "2 Etiketten")).toBeInTheDocument();
  });

  it("offers to book the old unbooked pieces out as Versehen, only while there are some", async () => {
    let unbooked = 2;
    store({
      [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: [stockLine(unbooked)] }),
      [`GET ${INVENTORY}/units`]: () => jsonResponse({ items: [{ id: "u1" }, { id: "u2" }], more: false }),
      [`POST ${INVENTORY}/units/scraps`]: () => {
        unbooked = 0;
        return jsonResponse({ scrapped: 2, already_scrapped: 0 });
      },
    });
    vi.stubGlobal("confirm", () => true);
    const user = userEvent.setup();
    renderWithQueryClient(<InventoryOverview staffRole="staff" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Alle als Versehen ausbuchen" }));

    expect(await screen.findByText("2 Stücke als Versehen ausgebucht.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, `POST ${INVENTORY}/units/scraps`)[0]?.body).toEqual({
      unit_ids: ["u1", "u2"],
      reason: "mistake",
      note: "Alter Ablauf",
    });
    await waitFor(() => expect(requestsTo(fetchMock, `GET ${INVENTORY}/stock`).length).toBeGreaterThan(1));
  });
});
