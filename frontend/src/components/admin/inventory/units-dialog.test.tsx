import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationNodeOut, UnitOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { UnitsDialog, usualPlace } from "./units-dialog";

const fetchMock = vi.fn<typeof fetch>();
const UNITS = "POST /api/v1/admin/inventory/units";
const LABELS = "POST /api/v1/admin/inventory/labels";
const VARIANT = { variantId: "v1", title: "Stellwerk Altenau · H0 · bemalt", sku: "MB-000006-H0-B" };

function place(code: string): LocationNodeOut {
  return {
    id: `loc-${code}`,
    parent_id: "loc-R01",
    code,
    path: `LAGER.${code.replace("-", ".")}`,
    kind: "compartment",
    name: "",
    depth: 2,
    holds_goods: true,
    unit_count: 0,
    total_count: 0,
    part_count: 0,
  };
}

function unit(id: string, code: string | null, status: UnitOut["status"] = "in_stock"): UnitOut {
  const location = code === null ? null : place(code);
  return {
    id,
    code: `7KQ2X9F4M${id}`,
    display_code: `7KQ2 X9F4 M${id}`,
    status,
    variant_id: "v1",
    variant: null,
    location,
    order_id: null,
    order_number: null,
    scrap_note: "",
    scrap_reason: null,
    created_at: "2026-11-15T10:00:00Z",
    updated_at: "2026-11-15T10:00:00Z",
  };
}

function store(lying: UnitOut[]) {
  routeFetch(fetchMock, {
    "GET /api/v1/admin/inventory/locations": () => jsonResponse({ items: [place("R01-F01"), place("R01-F02")] }),
    "GET /api/v1/admin/inventory/units": () => jsonResponse({ items: lying, more: false }),
    [UNITS]: ({ body }) => {
      const { quantity, location_code: code } = body as { quantity: number; location_code: string };
      return jsonResponse({ items: Array.from({ length: quantity }, (_, index) => unit(String(index), code)) }, 201);
    },
    [LABELS]: () => new Response("%PDF", { status: 200, headers: { "Content-Type": "application/pdf" } }),
  });
}

async function open(user: ReturnType<typeof userEvent.setup>) {
  renderWithQueryClient(<UnitsDialog variant={VARIANT} trigger={<button type="button">Öffnen</button>} />);
  await user.click(screen.getByRole("button", { name: "Öffnen" }));
  return screen.findByRole("dialog", { name: "Stücke einbuchen" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:1", revokeObjectURL: vi.fn() }));
  window.localStorage.clear();
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("UnitsDialog", () => {
  it("books the counted pieces into the place the model lies in, then prints its labels", async () => {
    store([unit("a", "R01-F01"), unit("b", "R01-F02"), unit("c", "R01-F02", "allocated")]);
    const user = userEvent.setup();
    const dialog = await open(user);

    const where = within(dialog).getByLabelText("Platz");
    await waitFor(() => expect(where).toHaveValue("R01-F02"));
    expect(within(dialog).getByText(/Hier liegt das Modell schon/)).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: /Etiketten drucken/ })).toBeChecked();
    const count = within(dialog).getByLabelText("Anzahl");
    await user.clear(count);
    await user.type(count, "3");
    await user.click(within(dialog).getByRole("button", { name: "Einbuchen und Etiketten drucken" }));

    expect(await screen.findByRole("heading", { name: "3 Stücke eingebucht" })).toBeInTheDocument();
    expect(requestsTo(fetchMock, UNITS)[0]?.body).toEqual({ variant_id: "v1", quantity: 3, location_code: "R01-F02" });
    expect(screen.getByText(/Liegen in R01-F02 und sind im Shop lieferbar/)).toBeInTheDocument();
    // The model's labels, one per piece, without a piece's code.
    expect(screen.queryByText(/7KQ2/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Etiketten als PDF" }));
    await screen.findByRole("link", { name: "PDF öffnen" });
    expect(requestsTo(fetchMock, LABELS)[0]?.body).toMatchObject({
      unit_codes: [],
      variants: [{ variant_id: "v1", quantity: 3 }],
    });
    expect(window.localStorage.getItem("mb-einbuchen-platz")).toBe("R01-F02");
  });

  it("needs a place, offers the last one used, and books without labels when asked", async () => {
    window.localStorage.setItem("mb-einbuchen-platz", "R01-F01");
    store([]);
    const user = userEvent.setup();
    const dialog = await open(user);

    const where = within(dialog).getByLabelText("Platz");
    await waitFor(() => expect(where).toHaveValue("R01-F01"));
    await user.selectOptions(where, "");
    await user.click(within(dialog).getByRole("button", { name: "Einbuchen und Etiketten drucken" }));
    expect(await within(dialog).findByText("Bitte den Platz wählen, in dem die Stücke liegen.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, UNITS)).toHaveLength(0);
    // "Später beim Einlagern scannen" is gone: pieces are always booked into a place.
    expect(within(where).queryByRole("option", { name: /Später/ })).toBeNull();

    await user.selectOptions(where, "R01-F01");
    await user.click(within(dialog).getByRole("checkbox", { name: /Etiketten drucken/ }));
    await user.click(within(dialog).getByRole("button", { name: "Einbuchen" }));

    expect(await screen.findByRole("heading", { name: "1 Stück eingebucht" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Etiketten als PDF" })).toBeNull();
    expect(requestsTo(fetchMock, LABELS)).toHaveLength(0);
  });
});

describe("usualPlace", () => {
  it("is where most pieces of the model lie, the first of them on a tie", () => {
    expect(usualPlace([])).toBeNull();
    expect(usualPlace([unit("a", "R01-F02"), unit("b", "R01-F01")])).toBe("R01-F02");
    expect(usualPlace([unit("a", "R01-F02"), unit("b", "R01-F01"), unit("c", "R01-F01")])).toBe("R01-F01");
    expect(usualPlace([unit("a", null, "labeled")])).toBeNull();
  });
});
