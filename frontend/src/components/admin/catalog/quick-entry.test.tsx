import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ProductListItemOut,
  ProductOut,
  QuickEntryOut,
  ReferencesOut,
  UnitOut,
  VariantOut,
} from "@/lib/api/generated/model";
import { requestsTo, routeFetch, type RouteHandler } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { QuickEntryDesk } from "./quick-entry";

const fetchMock = vi.fn<typeof fetch>();

const QUICK = "POST /api/v1/admin/catalog/quick-entries";
const UNITS = "POST /api/v1/admin/inventory/units";

const REFERENCES: ReferencesOut = {
  scales: [
    { code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 },
    { code: "TT", name: "TT", ratio: "1:120", ratio_denominator: 120, track_gauge_mm: 12 },
  ],
  finishes: [
    { code: "unpainted", name: "Bausatz", sku_letter: "B", colored: false, offered: true },
    { code: "painted", name: "Fertigmodell", sku_letter: "F", colored: true, offered: true },
    { code: "primed", name: "grundiert", sku_letter: "G", colored: false, offered: false },
  ],
  epochs: [],
};

function variant(overrides: Partial<VariantOut>): VariantOut {
  return {
    id: "v1",
    finish_code: "painted",
    color: "",
    sku: "MB-000007-TT-F",
    gtin: "2000000000077",
    price_cents: 3000,
    compare_at_price_cents: null,
    active: true,
    allow_backorder: false,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
    ...overrides,
  };
}

function product(overrides: Partial<ProductOut>): ProductOut {
  return {
    id: "p1",
    number: 7,
    name: "IFA W50 Kipper",
    slug: "ifa-w50-kipper",
    status: "draft",
    summary: "",
    description: "",
    prototype: "",
    primary_category_id: "c2",
    epoch_codes: [],
    scales: [],
    media: [],
    publish_blockers: ["no_main_image"],
    published_at: null,
    archived_at: null,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
    version: 1,
    ...overrides,
  };
}

function listItem(of: ProductOut): ProductListItemOut {
  return {
    id: of.id,
    number: of.number,
    name: of.name,
    slug: of.slug,
    status: of.status,
    main_image: null,
    price_from_cents: null,
    published_at: null,
    scale_codes: of.scales.map((s) => s.scale_code),
    updated_at: of.updated_at,
    variant_count: 0,
  };
}

const PUMA = product({
  id: "p5",
  number: 5,
  name: "ADK III3 Puma Kran-2",
  slug: "adk-iii3-puma-kran-2",
  scales: [
    {
      id: "s5",
      scale_code: "H0",
      length_mm: null,
      width_mm: null,
      height_mm: null,
      weight_g: null,
      variants: [
        variant({ id: "v5", color: "Grün", sku: "MB-000005-H0-F", price_cents: 6500 }),
        variant({ id: "v6", color: "Blau", sku: "MB-000005-H0-F2", price_cents: 6500 }),
      ],
    },
  ],
});

const UNIT: UnitOut = {
  id: "u1",
  code: "7K3M9QX2TA",
  display_code: "7K3M 9QX2 TA",
  status: "labeled",
  variant_id: "v1",
  variant: null,
  location: null,
  order_id: null,
  order_number: null,
  scrap_note: "",
  created_at: "2026-10-28T10:00:00Z",
  updated_at: "2026-10-28T10:00:00Z",
};

function desk(routes: Record<string, RouteHandler>) {
  routeFetch(fetchMock, {
    "GET /api/v1/admin/catalog/references": () => jsonResponse(REFERENCES),
    "GET /api/v1/admin/categories": () =>
      jsonResponse([
        { id: "c1", name: "Lkw", parent_id: null, position: 0, slug: "lkw" },
        { id: "c2", name: "Kipper", parent_id: "c1", position: 0, slug: "kipper" },
      ]),
    "GET /api/v1/admin/inventory/locations": () => jsonResponse({ items: [] }),
    ...routes,
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("QuickEntryDesk", () => {
  it("creates a new model in its colour, with a labelled piece, in one go", async () => {
    const created = product({
      scales: [
        {
          id: "s1",
          scale_code: "TT",
          length_mm: null,
          width_mm: null,
          height_mm: null,
          weight_g: null,
          variants: [variant({ color: "Gelb" })],
        },
      ],
    });
    const answer: QuickEntryOut = {
      product: created,
      variant: variant({ color: "Gelb" }),
      new_product: true,
      new_variant: true,
    };
    desk({
      "GET /api/v1/admin/products": () => jsonResponse({ items: [], next_cursor: null }),
      [QUICK]: () => jsonResponse(answer, 201),
      [UNITS]: () => jsonResponse({ items: [UNIT] }, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<QuickEntryDesk />);

    await user.type(await screen.findByLabelText("Name oder Nummer"), "IFA W50 Kipper");
    await user.click(await screen.findByRole("button", { name: "„IFA W50 Kipper“ neu anlegen" }));
    await user.selectOptions(screen.getByLabelText("Kategorie"), "c2");
    // A new model starts with nothing chosen: a guess would file it under the first scale.
    expect(screen.getByText("Noch Maßstab und Ausführung antippen.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "H0 · 1:87" })).not.toBeChecked();
    await user.click(screen.getByRole("radio", { name: "TT · 1:120" }));
    await user.click(screen.getByRole("radio", { name: "Fertigmodell" }));
    // The retired finish is not offered any more.
    expect(screen.queryByRole("radio", { name: "grundiert" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Gelb" }));
    await user.type(screen.getByLabelText("Preis"), "30");
    expect(screen.getByText("Neues Produkt mit TT · Fertigmodell, Gelb")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Erfassen · 1 Etikett" }));

    const done = await screen.findByRole("region", { name: "Erfasst" });
    expect(requestsTo(fetchMock, QUICK)[0]?.body).toEqual({
      product_id: null,
      name: "IFA W50 Kipper",
      category_id: "c2",
      scale_code: "TT",
      finish_code: "painted",
      color: "Gelb",
      price_cents: 3000,
      asset_id: null,
    });
    expect(requestsTo(fetchMock, UNITS)[0]?.body).toEqual({ variant_id: "v1", quantity: 1, location_code: null });
    expect(within(done).getByText("MB-000007-TT-F")).toBeInTheDocument();
    expect(within(done).getByText("Neues Produkt")).toBeInTheDocument();
    expect(within(done).getByText("7K3M 9QX2 TA")).toBeInTheDocument();
    expect(screen.getByText("1 erfasst · 1 Stück")).toBeInTheDocument();
  });

  it("takes a draft from the catalogue and offers the price of a variant that exists", async () => {
    const answer: QuickEntryOut = {
      product: PUMA,
      variant: variant({ id: "v6", color: "Blau", sku: "MB-000005-H0-F2", price_cents: 6900 }),
      new_product: false,
      new_variant: false,
    };
    desk({
      "GET /api/v1/admin/products": () => jsonResponse({ items: [listItem(PUMA)], next_cursor: null }),
      "GET /api/v1/admin/products/p5": () => jsonResponse(PUMA),
      [QUICK]: () => jsonResponse(answer, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<QuickEntryDesk />);

    await user.type(await screen.findByLabelText("Name oder Nummer"), "Puma");
    await user.click(await screen.findByRole("button", { name: /ADK III3 Puma Kran-2/ }));
    // A model from the catalogue brings its own scale and finish.
    await waitFor(() => expect(screen.getByRole("radio", { name: "H0 · 1:87" })).toBeChecked());
    expect(screen.getByRole("radio", { name: "Fertigmodell" })).toBeChecked();
    // The product's own colours come first.
    const paints = screen.getByRole("list", { name: "Häufige Farben" });
    expect(
      within(paints)
        .getAllByRole("button")
        .slice(0, 2)
        .map((button) => button.textContent),
    ).toEqual(["Blau", "Grün"]);
    await user.click(within(paints).getByRole("button", { name: "Blau" }));

    const price = screen.getByLabelText("Preis");
    expect(price).toHaveValue("65,00");
    expect(screen.getByText(/gibt es schon \(MB-000005-H0-F2\)/)).toBeInTheDocument();
    // A model already in the catalogue keeps its category: no field for it.
    expect(screen.queryByLabelText("Kategorie")).not.toBeInTheDocument();

    await user.clear(price);
    await user.type(price, "69");
    await user.click(screen.getByRole("button", { name: "Eins weniger" }));
    await user.click(screen.getByRole("button", { name: "Erfassen" }));

    await screen.findByRole("region", { name: "Erfasst" });
    expect(requestsTo(fetchMock, QUICK)[0]?.body).toMatchObject({
      product_id: "p5",
      name: null,
      color: "Blau",
      price_cents: 6900,
    });
    expect(requestsTo(fetchMock, UNITS)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Gleiches Modell, andere Farbe" }));
    await waitFor(() => expect(screen.getByText("ADK III3 Puma Kran-2")).toBeInTheDocument());
  });
  it("names the colour of a model from the start inventory and brings its price along", async () => {
    const crane = product({
      id: "p17",
      number: 17,
      name: "IFA ADK 70 Autokran",
      slug: "ifa-adk-70-autokran",
      scales: [
        {
          id: "s17",
          scale_code: "H0",
          length_mm: null,
          width_mm: null,
          height_mm: null,
          weight_g: null,
          variants: [variant({ id: "v17", sku: "MB-000017-H0-F", price_cents: 8000 })],
        },
      ],
    });
    desk({
      "GET /api/v1/admin/products": () => jsonResponse({ items: [listItem(crane)], next_cursor: null }),
      "GET /api/v1/admin/products/p17": () => jsonResponse(crane),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<QuickEntryDesk />);

    await user.type(await screen.findByLabelText("Name oder Nummer"), "ADK 70");
    await user.click(await screen.findByRole("button", { name: /IFA ADK 70 Autokran/ }));
    await user.click(await screen.findByRole("button", { name: "Gelb" }));

    expect(
      screen.getByText("MB-000017-H0-F hat noch keine Farbe und wird zu H0 · Fertigmodell, Gelb"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Preis")).toHaveValue("80,00");
  });
});
