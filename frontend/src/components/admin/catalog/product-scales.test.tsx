import { QueryClientProvider } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProductOut, ReferencesOut, VariantOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { ProductScales } from "./product-scales";

const fetchMock = vi.fn<typeof fetch>();
const PRODUCTION = "GET /api/v1/admin/catalog/production";
const PATCH = "PATCH /api/v1/admin/variants/v1";

const REFERENCES: ReferencesOut = {
  scales: [{ code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 }],
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
    sku: "MB-000012-H0-F",
    gtin: "2000000000428",
    price_cents: 5490,
    compare_at_price_cents: null,
    active: true,
    allow_backorder: false,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
    ...overrides,
  };
}

function product(variants: VariantOut[]): ProductOut {
  return {
    id: "p12",
    number: 12,
    name: "Löschgruppenfahrzeug LF 16",
    slug: "loeschgruppenfahrzeug-lf-16",
    status: "active",
    summary: "",
    description: "",
    prototype: "",
    label: "adp",
    primary_category_id: "c1",
    epoch_codes: [],
    scales: [
      { id: "s1", scale_code: "H0", length_mm: null, width_mm: null, height_mm: null, weight_g: null, variants },
    ],
    media: [],
    publish_blockers: [],
    published_at: "2026-10-27T10:00:00Z",
    archived_at: null,
    created_at: "2026-10-27T10:00:00Z",
    updated_at: "2026-10-27T10:00:00Z",
    version: 7,
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ProductScales", () => {
  it("chooses how a variant is made again: the shop's lead time, its own, or not at all", async () => {
    const standard = product([variant({ color: "Feuerwehrrot", allow_backorder: true })]);
    const own = product([variant({ color: "Feuerwehrrot", allow_backorder: true, lead_time_min_weeks: 3, lead_time_max_weeks: 5 })]);
    let answer = own;
    routeFetch(fetchMock, {
      [PRODUCTION]: () => jsonResponse({ default_lead_time_min_weeks: 3, default_lead_time_max_weeks: 5 }),
      [PATCH]: () => jsonResponse(answer),
    });
    const user = userEvent.setup();
    const { rerender, queryClient } = renderWithQueryClient(<ProductScales product={standard} references={REFERENCES} />);

    const choice = screen.getByLabelText("Nachfertigen Fertigmodell, Feuerwehrrot");
    await waitFor(() => expect(within(choice).getByRole("option", { name: "Standard-Lieferzeit (3–5 Wochen)" })).toBeInTheDocument());
    expect(choice).toHaveValue("standard");

    // Its own lead time starts from the shop's; then it can be changed.
    await user.selectOptions(choice, "own");
    await waitFor(() => expect(requestsTo(fetchMock, PATCH)).toHaveLength(1));
    expect(requestsTo(fetchMock, PATCH)[0]?.body).toEqual({ allow_backorder: true, lead_time_min_weeks: 3, lead_time_max_weeks: 5 });
    rerender(
      <QueryClientProvider client={queryClient}>
        <ProductScales product={own} references={REFERENCES} />
      </QueryClientProvider>,
    );
    expect(screen.getByLabelText("Lieferzeit Fertigmodell, Feuerwehrrot: frühestens nach Wochen")).toHaveValue("3");

    answer = product([variant({ color: "Feuerwehrrot", allow_backorder: false })]);
    await user.selectOptions(choice, "none");
    await waitFor(() => expect(requestsTo(fetchMock, PATCH)).toHaveLength(2));
    expect(requestsTo(fetchMock, PATCH)[1]?.body).toEqual({ allow_backorder: false });

    await user.selectOptions(choice, "standard");
    await waitFor(() => expect(requestsTo(fetchMock, PATCH)).toHaveLength(3));
    expect(requestsTo(fetchMock, PATCH)[2]?.body).toEqual({ allow_backorder: true, lead_time_min_weeks: null, lead_time_max_weeks: null });
  });

  it("asks to name the colour of the unnamed model before a second one, and offers no primer", async () => {
    routeFetch(fetchMock, { [PRODUCTION]: () => jsonResponse({ default_lead_time_min_weeks: 2, default_lead_time_max_weeks: 4 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<ProductScales product={product([variant({})])} references={REFERENCES} />);

    const finishes = screen.getByLabelText("Neue Ausführung");
    expect(
      within(finishes)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Bausatz", "Fertigmodell"]);
    await user.selectOptions(finishes, "painted");
    await user.type(screen.getByPlaceholderText("z. B. Gelb"), "Elfenbein");
    await user.type(screen.getByPlaceholderText("49,90"), "89,90");
    await user.click(screen.getByRole("button", { name: "Ausführung anlegen" }));

    expect(screen.getByText("Gib zuerst MB-000012-H0-F eine Farbe; dann kann Elfenbein dazukommen.")).toHaveRole(
      "alert",
    );
    expect(requestsTo(fetchMock, "POST /api/v1/admin/product-scales/s1/variants")).toHaveLength(0);
  });
});
