import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationNodeOut, PlaceStockOut, StockLineOut, StockValueOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
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

const VALUE: StockValueOut = {
  pieces: 7,
  value_cents: 6 * 4990 + 2990,
  free_pieces: 6,
  free_cents: 5 * 4990 + 2990,
  reserved_pieces: 1,
  reserved_cents: 4990,
  unpriced_pieces: 2,
  by_finish: [
    { key: "painted", name: "Fertigmodell", pieces: 6, value_cents: 6 * 4990 },
    { key: "unpainted", name: "Bausatz", pieces: 1, value_cents: 2990 },
  ],
  by_scale: [{ key: "H0", name: "H0", pieces: 7, value_cents: 6 * 4990 + 2990 }],
  by_model: [{ key: "p1", name: "Stellwerk Altenau", pieces: 7, value_cents: 6 * 4990 + 2990 }],
  part_pieces: 1204,
  part_kinds: 12,
};

function store(routes: Record<string, RouteHandler> = {}) {
  routeFetch(fetchMock, {
    [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
    [`GET ${INVENTORY}/stock/places`]: () => jsonResponse({ items: [LINE] }),
    [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: [stockLine(0)] }),
    [`GET ${INVENTORY}/stock/value`]: () => jsonResponse(VALUE),
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
    renderWithQueryClient(<InventoryOverview staffRole="staff" onStreamClosed={vi.fn()} />);

    const shelf = await screen.findByRole("region", { name: "Regal 1" });
    const model = within(shelf).getByRole("link", { name: "Stellwerk Altenau · H0 · Bausatz" });
    expect(model).toHaveAttribute("href", "/admin/modelle/p1");
    expect(model.closest("li")).toHaveTextContent("7 (1 reserviert)");
    expect(screen.getByRole("region", { name: "Weitere Plätze" })).toHaveTextContent("Packtisch");
  });

  it("shows packers the models without links to a page they may not open", async () => {
    store();
    renderWithQueryClient(<InventoryOverview staffRole="packer" onStreamClosed={vi.fn()} />);

    const shelf = await screen.findByRole("region", { name: "Regal 1" });
    expect(within(shelf).getByText("Stellwerk Altenau · H0 · Bausatz").closest("li")).toHaveTextContent("7 (1 reserviert)");
    expect(within(shelf).queryByRole("link", { name: "Stellwerk Altenau · H0 · Bausatz" })).toBeNull();
    // Packers look; they make no shelves and count nothing.
    expect(screen.queryByRole("button", { name: "Neues Regal" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Zählen" })).toBeNull();
  });

  it("shows owner and staff what the store is worth, split and per model", async () => {
    store();
    renderWithQueryClient(<InventoryOverview staffRole="owner" onStreamClosed={vi.fn()} />);

    const panel = await screen.findByRole("region", { name: "Lagerwert" });
    expect(await within(panel).findByText("329,30 €", { selector: "p" })).toBeInTheDocument();
    expect(within(panel).getByRole("img")).toHaveAccessibleName(`${formatPrice(27940)} frei verkäuflich, ${formatPrice(4990)} reserviert`);
    const finishes = within(panel).getByRole("region", { name: "Nach Ausführung" });
    expect(within(finishes).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      `Fertigmodell6 Stück${formatPrice(29940)}`,
      `Bausatz1 Stück${formatPrice(2990)}`,
    ]);
    expect(within(panel).getByRole("link", { name: "Stellwerk Altenau" })).toHaveAttribute("href", "/admin/modelle/p1");
    expect(panel).toHaveTextContent("1.204 Teile in Boxen (12 Teilenummern)");
    expect(panel).toHaveTextContent("2 Stück gelöschter Modelle");
  });

  it("does not show packers the worth of the store", async () => {
    store();
    renderWithQueryClient(<InventoryOverview staffRole="packer" onStreamClosed={vi.fn()} />);

    await screen.findByRole("region", { name: "Regal 1" });
    expect(screen.queryByRole("region", { name: "Lagerwert" })).toBeNull();
    expect(requestsTo(fetchMock, `GET ${INVENTORY}/stock/value`)).toHaveLength(0);
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
