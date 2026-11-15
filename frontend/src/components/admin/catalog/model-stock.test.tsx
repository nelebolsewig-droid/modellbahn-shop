import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationNodeOut, PlaceStockOut, StockHistoryRowOut } from "@/lib/api/generated/model";
import { productOut, REFERENCES, variantOut } from "@/test/catalog";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { ModelHistory, ModelStock, signed } from "./model-stock";

const fetchMock = vi.fn<typeof fetch>();
const INVENTORY = "/api/v1/admin/inventory";

function location(code: string, name: string): LocationNodeOut {
  return {
    id: `l-${code}`,
    code,
    path: `LAGER.${code.replace("-", ".")}`,
    kind: "compartment",
    name,
    parent_id: "l-R01",
    holds_goods: true,
    depth: 2,
    unit_count: 0,
    total_count: 0,
    part_count: 0,
    place: `Regal 1, ${name}`,
  };
}

const TOP = location("R01-B01", "Boden 1");
const BOTTOM = location("R01-B02", "Boden 2");

const LINE: PlaceStockOut = {
  location: TOP,
  place: "Regal 1, Boden 1",
  variant_id: "v1",
  variant: null,
  free: 3,
  reserved: 1,
};

function store() {
  routeFetch(fetchMock, {
    [`GET ${INVENTORY}/stock/places`]: () => jsonResponse({ items: [LINE] }),
    [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: [] }),
    [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: [TOP, BOTTOM] }),
    [`POST ${INVENTORY}/stock/moves`]: () => jsonResponse({ moved: 2, from_location: TOP, to_location: BOTTOM }),
    [`POST ${INVENTORY}/stock/counts`]: () => jsonResponse({ missing: 1, added: 0, reserved: 0 }),
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Bestand of a model", () => {
  it("shows each Ausführung with its places, free and reserved", async () => {
    store();
    renderWithQueryClient(<ModelStock product={productOut({}, [variantOut()])} references={REFERENCES} />);

    const row = (await screen.findByRole("link", { name: /Regal 1, Boden 1/ })).closest("li") as HTMLElement;
    expect(row).toHaveTextContent("3 frei · 1 reserviert");
    expect(screen.getByText("H0 · Bausatz")).toBeInTheDocument();
    for (const action of ["Einbuchen", "Ausbuchen", "Etiketten", "Zählen"]) {
      expect(screen.getAllByRole("button", { name: action }).length).toBeGreaterThan(0);
    }
  });

  it("moves a number of pieces to another place", async () => {
    store();
    const user = userEvent.setup();
    renderWithQueryClient(<ModelStock product={productOut({}, [variantOut()])} references={REFERENCES} />);
    const row = (await screen.findByRole("link", { name: /Regal 1, Boden 1/ })).closest("li") as HTMLElement;

    await user.click(within(row).getByRole("button", { name: "Umlagern" }));
    const dialog = await screen.findByRole("dialog", { name: "Umlagern" });
    const count = within(dialog).getByLabelText("Anzahl");
    expect(count).toHaveValue("4");
    await user.clear(count);
    await user.type(count, "2");
    await waitFor(() => expect(within(dialog).getByRole("option", { name: /Regal 1, Boden 2/ })).toBeInTheDocument());
    await user.selectOptions(within(dialog).getByLabelText("Nach"), "R01-B02");
    await user.click(within(dialog).getByRole("button", { name: "Umlagern" }));

    expect(await screen.findByText("2 nach R01-B02 umgelagert.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, `POST ${INVENTORY}/stock/moves`)[0]?.body).toEqual({
      variant_id: "v1",
      from_location: "R01-B01",
      to_location: "R01-B02",
      quantity: 2,
    });
  });

  it("books the counted number; the difference goes out", async () => {
    store();
    const user = userEvent.setup();
    renderWithQueryClient(<ModelStock product={productOut({}, [variantOut()])} references={REFERENCES} />);
    await screen.findByRole("link", { name: /Regal 1, Boden 1/ });

    await user.click(screen.getByRole("button", { name: "Zählen" }));
    const dialog = await screen.findByRole("dialog", { name: /Zählen/ });
    const counted = within(dialog).getByLabelText("H0 · Bausatz · Regal 1, Boden 1");
    expect(counted).toHaveValue("4");
    await user.clear(counted);
    await user.type(counted, "3");
    await user.click(within(dialog).getByRole("button", { name: "Zählung buchen" }));

    expect(await screen.findByText("1 fehlendes Stück ausgebucht.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, `POST ${INVENTORY}/stock/counts`)[0]?.body).toEqual({
      lines: [{ variant_id: "v1", location_code: "R01-B01", expected: 4, counted: 3 }],
    });
  });
});

describe("Verlauf of a model", () => {
  const row = (change: Partial<StockHistoryRowOut>): StockHistoryRowOut => ({
    occurred_at: "2026-11-15T10:00:00Z",
    staff_name: "Johann",
    reason: "put_away",
    variant_id: "v1",
    variant: null,
    quantity: 3,
    from_location: null,
    from_place: null,
    to_location: "R01-B01",
    to_place: "Regal 1, Boden 1",
    scan: false,
    ...change,
  });

  it("signs what a booking did", () => {
    expect(signed(row({}))).toBe("+3");
    expect(signed(row({ reason: "scrap", from_location: "R01-B01", to_location: null }))).toBe("−3");
    expect(signed(row({ reason: "move", from_location: "R01-B01" }))).toBe("3");
  });

  it("lists the bookings, without the labelling that comes with booking in", async () => {
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/stock/history`]: () =>
        jsonResponse({
          items: [
            row({ reason: "move", quantity: 2, from_location: "R01-B01", from_place: "Regal 1, Boden 1", to_place: "Regal 1, Boden 2" }),
            row({}),
            row({ reason: "label", to_location: null, to_place: null }),
          ],
        }),
    });
    renderWithQueryClient(<ModelHistory productId="p1" />);

    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Umgelagert · Regal 1, Boden 1 → Regal 1, Boden 2");
    expect(items[1]).toHaveTextContent("+3");
    expect(items[1]).toHaveTextContent("Johann");
  });
});
